"""The HTTP API through FastAPI's test client, with the fake model and the fake ordering server."""

import time

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from tests.support.builders import make_runtime
from tests.support.fake_order_server import FakeOrderServer


def client_with(*steps: LLMResponse) -> tuple[TestClient, FakeOrderServer]:
    server = FakeOrderServer()
    runtime = make_runtime(FakeLLM(steps), server)
    return TestClient(create_app(runtime)), server


def start(client: TestClient) -> dict:
    response = client.post("/api/sessions")
    assert response.status_code == 201, response.text
    return response.json()


def test_starting_a_session_needs_no_login_and_greets_an_unknown_customer() -> None:
    client, server = client_with()
    body = start(client)
    assert body["session_id"] and body["status"] == "open"
    assert body["customer"] is None and body["order"] is None and body["idle_timeout_s"] > 0
    assert body["greeting"].startswith("Welcome to McDonald's Nemi Nagar!")
    assert server.requests == [("GET", "/catalog/version")]  # only the menu version is checked


def test_a_message_gets_a_reply_and_a_trace() -> None:
    client, _ = client_with(LLMResponse(text="Hello."))
    sid = start(client)["session_id"]
    response = client.post(f"/api/sessions/{sid}/messages", json={"text": "hi"})
    body = response.json()
    assert response.status_code == 200 and body["text"] == "Hello."
    assert body["stop_reason"] == "answered"
    assert [e["event"] for e in body["trace"]][:2] == ["GuardDecided", "TurnStarted"]


def test_an_order_shows_up_in_the_session_afterwards() -> None:
    add = LLMResponse(
        tool_calls=[ToolCall(id="c", name="add_to_order", arguments={"dish_id": 4, "quantity": 2})]
    )
    client, _ = client_with(add, LLMResponse(text="Added."))
    sid = start(client)["session_id"]
    assert client.get(f"/api/sessions/{sid}").json()["order"] is None
    client.post(f"/api/sessions/{sid}/messages", json={"text": "two tikki burgers"})
    order = client.get(f"/api/sessions/{sid}").json()["order"]
    assert order["status"] == "draft" and order["total"] == 160.0
    assert [(i["name"], i["quantity"], i["line_total"]) for i in order["lines"]] == [
        ("McAloo Tikki", 2, 152.38)
    ]


def test_a_placed_order_closes_the_session_and_shows_its_number() -> None:
    steps = [
        LLMResponse(tool_calls=[ToolCall(id="a", name="add_to_order", arguments={"dish_id": 4})]),
        LLMResponse(tool_calls=[ToolCall(id="p", name="place_order", arguments={})]),
        LLMResponse(text="Your number is 14."),
    ]
    client, _ = client_with(*steps)
    sid = start(client)["session_id"]
    client.post(f"/api/sessions/{sid}/messages", json={"text": "one tikki, place it"})
    shown = client.get(f"/api/sessions/{sid}").json()
    assert shown["status"] == "placed" and shown["order"]["order_number"] == 14
    again = client.post(f"/api/sessions/{sid}/messages", json={"text": "and a coke"})
    assert again.status_code == 409 and "placed" in again.json()["detail"]


def test_an_empty_message_is_rejected_and_a_blank_one_is_refused_by_the_guard() -> None:
    client, _ = client_with()
    sid = start(client)["session_id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": ""}).status_code == 422
    blank = client.post(f"/api/sessions/{sid}/messages", json={"text": "   "}).json()
    assert blank["stop_reason"] == "refused"


def test_unknown_sessions_are_not_found() -> None:
    client, _ = client_with()
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.post("/api/sessions/nope/messages", json={"text": "hi"}).status_code == 404


def test_a_second_message_while_a_reply_is_being_written_is_turned_away() -> None:
    client, _ = client_with(LLMResponse(text="x"))
    sid = start(client)["session_id"]
    lock = client.app.state.store.get(sid).lock
    lock.acquire()  # what a running turn holds
    try:
        assert client.post(f"/api/sessions/{sid}/messages", json={"text": "hi"}).status_code == 409
    finally:
        lock.release()


def test_each_customer_gets_their_own_session_and_order() -> None:
    client, _ = client_with()
    first, second = start(client)["session_id"], start(client)["session_id"]
    assert first != second
    store = client.app.state.store
    assert store.get(first).session is not store.get(second).session


def test_ending_a_session_cancels_its_draft_and_forgets_it() -> None:
    add = LLMResponse(tool_calls=[ToolCall(id="c", name="add_to_order", arguments={"dish_id": 4})])
    client, server = client_with(add, LLMResponse(text="Added."))
    sid = start(client)["session_id"]
    client.post(f"/api/sessions/{sid}/messages", json={"text": "one tikki"})
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert server.status == "cancelled"  # the draft was not left open
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 204  # twice is harmless


def test_the_app_ends_idle_chats_while_it_runs() -> None:
    server = FakeOrderServer()
    runtime = make_runtime(FakeLLM([]), server)
    with TestClient(create_app(runtime, idle_timeout_s=1)) as client:
        sid = start(client)["session_id"]
        for _ in range(40):  # the sweep runs every second at this timeout
            time.sleep(0.1)
            if client.get(f"/api/sessions/{sid}").status_code == 404:
                break
        assert client.get(f"/api/sessions/{sid}").status_code == 404
