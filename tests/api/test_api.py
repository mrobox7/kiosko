"""The HTTP API through FastAPI's test client, with the fake model and fake backend."""

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.session.factory import Runtime
from tests.support.builders import clock, make_loop
from tests.support.fake_backend import FakeBackend

SLOT = "2030-06-10T19:30:00"
PRIYA = {"phone": "+91-9876543210"}


def client_with(*steps: LLMResponse) -> tuple[TestClient, FakeBackend]:
    backend = FakeBackend()
    runtime = Runtime(backend=backend.client, loop=make_loop(FakeLLM(steps)), clock=clock)
    return TestClient(create_app(runtime)), backend


def login(client: TestClient, **who: str) -> dict:
    response = client.post("/api/login", json=who or PRIYA)
    assert response.status_code == 200, response.text
    return response.json()


def test_login_starts_a_chat_with_greeting_profile_and_bookings() -> None:
    client, backend = client_with()
    backend.add_reservation(1, 7, SLOT, 4)
    body = login(client)
    assert body["customer"]["name"] == "Priya Sharma" and body["session_id"]
    assert body["greeting"].startswith("Welcome, Priya.")
    assert {"label": "Seating preference", "value": "outdoor"} in body["remembered"]
    assert [b["id"] for b in body["upcoming"]] == [1]
    assert body["upcoming"][0]["slot_datetime"] == SLOT


def test_login_needs_a_phone_or_email() -> None:
    client, _ = client_with()
    response = client.post("/api/login", json={"name": "Nobody"})
    assert response.status_code == 422 and "phone number or an email" in response.json()["detail"]


def test_a_new_customer_is_created_at_login() -> None:
    client, backend = client_with()
    body = login(client, name="Asha Rao", phone="+91-9000000001")
    assert body["customer"]["name"] == "Asha Rao" and len(backend.customers) == 4


def test_a_message_gets_a_reply_and_a_trace() -> None:
    client, _ = client_with(LLMResponse(text="Hello Priya."))
    sid = login(client)["session_id"]
    response = client.post(f"/api/sessions/{sid}/messages", json={"text": "hi"})
    body = response.json()
    assert response.status_code == 200 and body["text"] == "Hello Priya."
    assert body["stop_reason"] == "answered"
    assert [e["event"] for e in body["trace"]][:2] == ["GuardDecided", "TurnStarted"]


def test_a_booking_shows_up_in_the_session_afterwards() -> None:
    book = LLMResponse(
        tool_calls=[
            ToolCall(
                id="c",
                name="create_reservation",
                arguments={"slot_datetime": SLOT, "party_size": 4, "location": "outdoor"},
            )
        ]
    )
    client, _ = client_with(book, LLMResponse(text="Booked."))
    sid = login(client)["session_id"]
    assert client.get(f"/api/sessions/{sid}").json()["upcoming"] == []
    client.post(f"/api/sessions/{sid}/messages", json={"text": "book outdoor for 4"})
    upcoming = client.get(f"/api/sessions/{sid}").json()["upcoming"]
    assert [(b["party_size"], b["slot_datetime"]) for b in upcoming] == [(4, SLOT)]


def test_an_empty_message_is_rejected_and_a_blank_one_is_refused_by_the_guard() -> None:
    client, _ = client_with()
    sid = login(client)["session_id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": ""}).status_code == 422
    blank = client.post(f"/api/sessions/{sid}/messages", json={"text": "   "}).json()
    assert blank["stop_reason"] == "refused"


def test_unknown_sessions_are_not_found() -> None:
    client, _ = client_with()
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.post("/api/sessions/nope/messages", json={"text": "hi"}).status_code == 404
    assert client.post("/api/sessions/nope/new").status_code == 404


def test_a_second_message_while_a_reply_is_being_written_is_turned_away() -> None:
    client, _ = client_with(LLMResponse(text="x"))
    sid = login(client)["session_id"]
    lock = client.app.state.store.get(sid).lock
    lock.acquire()  # what a running turn holds
    try:
        assert client.post(f"/api/sessions/{sid}/messages", json={"text": "hi"}).status_code == 409
        assert client.post(f"/api/sessions/{sid}/new").status_code == 409
    finally:
        lock.release()


def test_a_new_chat_forgets_the_conversation_but_keeps_the_customer() -> None:
    client, _ = client_with(LLMResponse(text="One."), LLMResponse(text="Two."))
    sid = login(client)["session_id"]
    client.post(f"/api/sessions/{sid}/messages", json={"text": "hi"})
    assert client.app.state.store.get(sid).session.history
    body = client.post(f"/api/sessions/{sid}/new").json()
    assert body["session_id"] == sid and body["customer"]["name"] == "Priya Sharma"
    assert body["greeting"].startswith("Welcome, Priya.")
    assert client.app.state.store.get(sid).session.history == []


def test_ending_a_session_forgets_it() -> None:
    client, _ = client_with()
    sid = login(client)["session_id"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
