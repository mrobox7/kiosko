"""The kiosk routes through FastAPI's test client: the menu to browse and the taps on the cart."""

import time

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.llm.contract import LLMResponse
from tests.support.builders import make_runtime, plan, say
from tests.support.fake_llm import FakeLLM
from tests.support.fake_order_server import FakeOrderServer

TIKKI = {"dish_id": 4, "options": [{"option_id": 1}]}  # McAloo Tikki with ketchup


def kiosk(*steps: LLMResponse) -> tuple[TestClient, str, FakeLLM]:
    llm = FakeLLM(steps)
    client = TestClient(create_app(make_runtime(llm, FakeOrderServer())))
    return client, client.post("/api/sessions").json()["session_id"], llm


def test_the_menu_has_the_outlet_sections_pictures_and_choices() -> None:
    client, _, _ = kiosk()
    body = client.get("/api/menu").json()
    assert body["outlet"]["name"] == "McDonald's Nemi Nagar"
    assert [c["slug"] for c in body["categories"]] == ["burgers", "desserts"]
    tikki = next(d for d in body["dishes"] if d["id"] == 4)
    assert tikki["image_url"] == "/images/4.png"
    assert [g["name"] for g in tikki["option_groups"]] == ["Sauce", "Cheese"]
    assert [o["size"] for o in tikki["meal_offers"]] == ["Medium", "Large"]
    sauce = next(g for g in tikki["option_groups"] if g["name"] == "Sauce")
    assert [(o["name"], o["is_default"]) for o in sauce["options"]] == [
        ("Complimentary Ketchup", True),
        ("No Ketchup", False),
    ]  # the screen starts with the default picked


def test_tapping_a_dish_puts_it_on_the_order() -> None:
    client, sid, _ = kiosk()
    response = client.post(f"/api/sessions/{sid}/lines", json={**TIKKI, "quantity": 2})
    assert response.status_code == 201
    order = response.json()["order"]
    assert [(i["name"], i["quantity"]) for i in order["lines"]] == [("McAloo Tikki", 2)]
    assert order["lines"][0]["dish_id"] == 4  # so the screen can show the dish's picture
    assert client.get(f"/api/sessions/{sid}").json()["order"] == order


def test_a_missing_choice_is_refused_and_nothing_is_added() -> None:
    client, sid, _ = kiosk()
    response = client.post(f"/api/sessions/{sid}/lines", json={"dish_id": 5})  # no sauce
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "incomplete"
    assert client.get(f"/api/sessions/{sid}").json()["order"]["lines"] == []


def test_an_unknown_dish_is_refused() -> None:
    client, sid, _ = kiosk()
    assert client.post(f"/api/sessions/{sid}/lines", json={"dish_id": 999}).status_code == 422


def test_a_line_can_change_count_and_be_removed() -> None:
    client, sid, _ = kiosk()
    line = client.post(f"/api/sessions/{sid}/lines", json=TIKKI).json()["order"]["lines"][0]["id"]
    changed = client.patch(f"/api/sessions/{sid}/lines/{line}", json={"quantity": 3})
    assert changed.json()["order"]["lines"][0]["quantity"] == 3
    gone = client.delete(f"/api/sessions/{sid}/lines/{line}")
    assert gone.status_code == 200 and gone.json()["order"]["lines"] == []


def test_a_count_outside_the_limits_is_rejected() -> None:
    client, sid, _ = kiosk()
    line = client.post(f"/api/sessions/{sid}/lines", json=TIKKI).json()["order"]["lines"][0]["id"]
    assert (
        client.patch(f"/api/sessions/{sid}/lines/{line}", json={"quantity": 0}).status_code == 422
    )


def test_placing_gives_the_order_number_and_closes_the_order() -> None:
    client, sid, _ = kiosk()
    client.post(f"/api/sessions/{sid}/lines", json=TIKKI)
    placed = client.post(f"/api/sessions/{sid}/place").json()
    assert placed["status"] == "placed" and placed["order"]["order_number"]
    assert client.post(f"/api/sessions/{sid}/lines", json=TIKKI).status_code == 409


def test_placing_an_empty_order_is_refused() -> None:
    client, sid, _ = kiosk()
    response = client.post(f"/api/sessions/{sid}/place")
    assert response.status_code == 422 and response.json()["detail"]["code"] == "no_order"


def test_an_unknown_session_is_not_found() -> None:
    client, _, _ = kiosk()
    assert client.post("/api/sessions/nope/lines", json=TIKKI).status_code == 404


def test_the_assistant_sees_what_was_tapped_and_no_model_call_is_made() -> None:
    client, sid, llm = kiosk(plan({"type": "chat"}), say("Two, then."))
    client.post(f"/api/sessions/{sid}/lines", json=TIKKI)
    assert llm.calls == []  # a tap never calls the model
    client.post(f"/api/sessions/{sid}/messages", json={"text": "what do I have?"})
    context = next(m.text for m in llm.calls[0].messages if m.role == "system")
    assert "McAloo Tikki" in context


def test_a_tap_and_a_chat_change_the_same_order() -> None:
    add = plan({"type": "add_item", "dish": "Float", "options": ["Flavour 0"]})
    client, sid, _ = kiosk(add, say("Added."))
    client.post(f"/api/sessions/{sid}/lines", json=TIKKI)
    client.post(f"/api/sessions/{sid}/messages", json={"text": "and a float"})
    lines = client.get(f"/api/sessions/{sid}").json()["order"]["lines"]
    assert [i["name"] for i in lines] == ["McAloo Tikki", "Float"]


def test_a_keepalive_stops_an_order_being_ended_as_idle() -> None:
    runtime = make_runtime(FakeLLM([]), FakeOrderServer())
    with TestClient(create_app(runtime, idle_timeout_s=2)) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        for _ in range(6):  # three seconds in all, longer than the idle timeout
            time.sleep(0.5)
            assert client.post(f"/api/sessions/{sid}/keepalive").status_code == 204
        assert client.get(f"/api/sessions/{sid}").status_code == 200
    assert TestClient(create_app(runtime)).post("/api/sessions/nope/keepalive").status_code == 404
