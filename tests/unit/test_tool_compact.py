from typing import Any

from app.domain.results import ToolResult
from app.tools.base import Tool
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx
from tests.support.fake_backend import FakeBackend

REGISTRY = ToolRegistry.discover()
SLOT = "2030-06-10T19:30:00"


def run(name: str, args: dict[str, Any], backend: FakeBackend) -> ToolResult:
    return REGISTRY.dispatch(name, args, make_ctx(backend, 1))


def line(name: str, args: dict[str, Any], result: ToolResult) -> str:
    return REGISTRY.compact(name, args, result)


def book(b: FakeBackend) -> int:
    booked = run("create_reservation", {"table_id": 7, "slot_datetime": SLOT, "party_size": 2}, b)
    return int(booked.data["id"])


def test_default_is_ok_or_the_error_code() -> None:
    t = REGISTRY._tools["list_my_reservations"]  # noqa: SLF001
    args = t.args_model.model_validate({})
    assert Tool.compact(t, ToolResult.success({}), args) == "ok"
    failure = ToolResult.failure("not_permitted", "x")
    assert Tool.compact(t, failure, args) == "error: not_permitted"


def test_registry_degrades_when_args_do_not_validate() -> None:
    assert line("check_availability", {}, ToolResult.success({})) == "ok"


def test_menu_line_has_ids_prices_and_allergen_flags() -> None:
    result = run("list_menu", {}, FakeBackend())
    text = line("list_menu", {}, result)
    assert text.startswith(f"{len(result.data['items'])} dishes: ")
    assert "(nuts" in text or "(dairy" in text
    first = result.data["items"][0]
    assert f"{first['id']} {first['name']} {first['price']:g}" in text
    assert line("list_menu", {}, ToolResult.success({"items": []})) == "no dishes matched"


def test_availability_line_has_table_ids() -> None:
    args = {"slot_datetime": SLOT, "party_size": 2}
    text = line("check_availability", args, run("check_availability", args, FakeBackend()))
    assert text.startswith("free 2030-06-10 19:30: table ") and "seats" in text
    empty = ToolResult.success({"slot_datetime": SLOT, "tables": []})
    assert line("check_availability", args, empty) == "no tables free 2030-06-10 19:30"


def test_reservation_and_order_read_lines() -> None:
    b = FakeBackend()
    rid = book(b)
    mine = line("list_my_reservations", {}, run("list_my_reservations", {}, b))
    assert f"#{rid} 2030-06-10 19:30 party 2 table 7 confirmed" in mine

    items = [{"menu_item_id": 1, "quantity": 2}]
    run("add_order_items", {"reservation_id": rid, "items": items}, b)
    args = {"reservation_id": rid}
    orders = line("get_reservation_orders", args, run("get_reservation_orders", args, b))
    assert orders.startswith(f"booking #{rid}: order ") and "x2" in orders
    assert (
        line("get_reservation_orders", {"reservation_id": 3}, ToolResult.success({"orders": []}))
        == "booking #3: no orders"
    )
    assert (
        line("get_my_order_history", {}, ToolResult.success({"orders": [{}, {}]})) == "2 past items"
    )


def test_create_cancel_and_preferences_lines() -> None:
    b = FakeBackend()
    create = {"table_id": 7, "slot_datetime": SLOT, "party_size": 2}
    booked = run("create_reservation", create, b)
    rid = booked.data["id"]
    assert line("create_reservation", create, booked) == (
        f"Reservation #{rid} for 2 at 2030-06-10 19:30 (table 7)"
    )
    cancel = {"reservation_id": rid}
    assert line("cancel_reservation", cancel, run("cancel_reservation", cancel, b)) == (
        f"Reservation #{rid} cancelled"
    )
    prefs = {"seating": "outdoor", "allergies_add": ["shellfish"]}
    assert line("update_preferences", prefs, run("update_preferences", prefs, b)) == (
        "preferences saved, now: seating outdoor; dietary vegetarian; allergies shellfish"
    )
    same = {"seating": "outdoor"}
    assert line("update_preferences", same, run("update_preferences", same, b)) == (
        "preferences unchanged (already remembered)"
    )


def test_add_line_has_booking_and_order_ids_from_data_and_args() -> None:
    b = FakeBackend()
    rid = book(b)
    args = {
        "reservation_id": rid,
        "items": [{"menu_item_id": 1, "quantity": 1}, {"menu_item_id": 10, "quantity": 2}],
    }
    added = run("add_order_items", args, b)
    first, second = (a["order_id"] for a in added.data["added"])
    assert line("add_order_items", args, added) == (
        f"added to booking #{rid}: order {first} item #1 x1; order {second} item #10 x2"
    )


def test_add_line_names_refused_items() -> None:
    args = {"reservation_id": 1, "items": [{"menu_item_id": 1, "quantity": 1}]}
    result = ToolResult(
        ok=True,
        data={
            "added": [{"order_id": 5, "menu_item_id": 1, "quantity": 1}],
            "failed": [
                {"menu_item_id": 7, "code": "allergy_conflict", "allergen": "nuts"},
                {"menu_item_id": 9, "reason": "x"},
            ],
        },
    )
    assert line("add_order_items", args, result) == (
        "added to booking #1: order 5 item #1 x1; "
        "not added: item #7 (nuts allergy), item #9 (rejected)"
    )


def test_remove_line_carries_the_order_id() -> None:
    b = FakeBackend()
    rid = book(b)
    items = [{"menu_item_id": 10, "quantity": 2}]
    added = run("add_order_items", {"reservation_id": rid, "items": items}, b)
    order_id = added.data["added"][0]["order_id"]
    removed = run("remove_order_item", {"order_id": order_id}, b)
    assert line("remove_order_item", {"order_id": order_id}, removed) == (
        f"order {order_id}: removed item #10 x2 from booking #{rid}"
    )
