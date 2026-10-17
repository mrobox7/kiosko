"""Stage 3 tools: update_preferences, get_my_order_history, and the allergy guard."""

from app.domain.results import ToolResult
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx
from tests.support.fake_backend import FakeBackend

SLOT = "2030-06-10T19:30:00"
REG = ToolRegistry.discover()
KULFI, BUTTER_CHICKEN, ROTI, PANEER_TIKKA = 12, 6, 10, 1  # nuts+dairy, nuts+dairy, none, dairy


def run(name: str, args: dict, backend: FakeBackend, customer_id: int) -> ToolResult:
    return REG.dispatch(name, args, make_ctx(backend, customer_id))


def order(backend: FakeBackend, customer_id: int, *item_ids: int) -> ToolResult:
    rid = next(
        (r["id"] for r in backend.reservations.values() if r["customer_id"] == customer_id),
        None,
    ) or backend.add_reservation(customer_id, 7, SLOT)
    items = [{"menu_item_id": i} for i in item_ids]
    return run("add_order_items", {"reservation_id": rid, "items": items}, backend, customer_id)


def test_anita_cannot_order_a_nut_dish_even_by_name() -> None:
    b = FakeBackend()
    r = order(b, 3, KULFI)
    assert not r.ok and r.error and r.error.code == "allergy_conflict"
    assert r.data["failed"][0]["allergen"] == "nuts" and "Kulfi" in r.data["failed"][0]["reason"]
    assert [x for x in b.requests if x.method == "POST" and "/orders" in x.url.path] == []
    assert r.writes == []


def test_blocked_item_does_not_stop_the_rest_of_the_batch() -> None:
    b = FakeBackend()
    r = order(b, 3, BUTTER_CHICKEN, ROTI, KULFI)
    assert r.ok and [a["menu_item_id"] for a in r.data["added"]] == [ROTI]
    assert {f["menu_item_id"] for f in r.data["failed"]} == {BUTTER_CHICKEN, KULFI}
    assert len(r.writes) == 1


def test_customer_without_allergies_orders_the_same_dishes() -> None:
    assert order(FakeBackend(), 2, KULFI, BUTTER_CHICKEN).ok


def test_dairy_allergy_blocks_dairy_but_not_nuts() -> None:
    b = FakeBackend()
    run("update_preferences", {"allergies_add": ["dairy"], "allergies_remove": ["nuts"]}, b, 3)
    r = order(b, 3, PANEER_TIKKA, ROTI)
    assert [a["menu_item_id"] for a in r.data["added"]] == [ROTI]
    assert r.data["failed"][0]["allergen"] == "dairy"


def test_allergy_stated_earlier_in_the_same_turn_applies_immediately() -> None:
    b = FakeBackend()
    assert run("update_preferences", {"allergies_add": ["nuts"]}, b, 2).ok  # Rahul, same ctx style
    r = order(b, 2, KULFI)
    assert not r.ok and r.error and r.error.code == "allergy_conflict"


def test_uncheckable_allergies_are_flagged_in_the_result() -> None:
    b = FakeBackend()
    run("update_preferences", {"allergies_add": ["gluten", "shellfish"]}, b, 2)
    r = order(b, 2, ROTI)
    assert r.ok and r.data["unchecked_allergies"] == ["gluten", "shellfish"]
    assert "confirming with staff" in r.data["note"]


def test_if_allergies_cannot_be_read_the_order_is_refused() -> None:
    import httpx

    b = FakeBackend()
    rid = b.add_reservation(1, 7, SLOT)
    b.overrides.append(("GET", r"/customers/1", lambda r: httpx.Response(503, text="down")))
    r = run("add_order_items", {"reservation_id": rid, "items": [{"menu_item_id": ROTI}]}, b, 1)
    assert not r.ok and r.error and r.error.code == "backend_unavailable"
    assert b.orders == {}


def test_update_preferences_ledger_and_second_allergy_keeps_first() -> None:
    b = FakeBackend()
    r = run("update_preferences", {"allergies_add": ["shellfish"]}, b, 3)
    assert r.ok and r.data["saved"] and r.data["allergies"] == ["nuts", "shellfish"]
    assert r.writes[0].action == "preferences_updated"


def test_update_preferences_noop_and_empty() -> None:
    b = FakeBackend()
    again = run("update_preferences", {"seating": "outdoor"}, b, 1)  # Priya already has outdoor
    assert again.ok and again.data["saved"] is False and again.writes == []
    empty = run("update_preferences", {}, b, 1)
    assert not empty.ok and empty.error and empty.error.code == "invalid_arguments"


def test_update_preferences_rejects_values_outside_the_vocabulary() -> None:
    r = run("update_preferences", {"allergies_add": ["pollen"]}, FakeBackend(), 1)
    assert r.error and r.error.code == "invalid_arguments"


def test_order_history_newest_first_and_limited() -> None:
    b = FakeBackend()
    old = b.add_reservation(1, 7, "2030-06-05T19:00:00")
    new = b.add_reservation(1, 8, "2030-07-01T19:00:00")
    b.client.add_order(old, 1, 2)
    b.client.add_order(new, 5, 1)
    b.client.add_order(new, 10, 4)
    r = run("get_my_order_history", {"limit": 2}, b, 1)
    assert [(o["date"], o["item"]) for o in r.data["orders"]] == [
        ("2030-07-01", "Roti"), ("2030-07-01", "Dal Makhani")]  # fmt: skip
    assert "2 of 3" in r.data["note"]
