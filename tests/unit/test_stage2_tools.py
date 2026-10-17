import pytest

from app.domain.results import ToolResult
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx
from tests.support.fake_backend import FakeBackend

SLOT = "2030-06-10T19:30:00"
REG = ToolRegistry.discover()


def run(name: str, args: dict, backend: FakeBackend, customer_id: int = 1) -> ToolResult:
    return REG.dispatch(name, args, make_ctx(backend, customer_id))


def code(r: ToolResult) -> str | None:
    return r.error.code if r.error else None


def test_all_stage2_tools_registered() -> None:
    names = {s.name for s in REG.specs()}
    assert names == {
        "list_menu", "check_availability", "list_my_reservations", "create_reservation",
        "cancel_reservation", "add_order_items", "get_reservation_orders", "remove_order_item",
        "update_preferences", "get_my_order_history", "recommend_items",
    }  # fmt: skip


def test_customer_id_is_never_a_model_argument() -> None:
    for spec in REG.specs():
        assert "customer_id" not in spec.parameters.get("properties", {})


def test_check_availability_filters_by_party_and_location() -> None:
    r = run(
        "check_availability",
        {"slot_datetime": SLOT, "party_size": 4, "location": "outdoor"},
        FakeBackend(),
    )
    assert r.ok and {t["table_id"] for t in r.data["tables"]} == {7, 8}


def test_slot_with_utc_offset_is_rejected() -> None:
    r = run(
        "check_availability", {"slot_datetime": SLOT + "+05:30", "party_size": 2}, FakeBackend()
    )
    assert code(r) == "invalid_arguments"


def test_create_reservation_binds_customer_and_writes_ledger() -> None:
    b = FakeBackend()
    r = run("create_reservation", {"table_id": 7, "slot_datetime": SLOT, "party_size": 4}, b)
    assert r.ok and b.reservations[1]["customer_id"] == 1
    assert r.writes[0].action == "created" and r.writes[0].state.table_id == 7  # type: ignore[union-attr]


def test_create_reservation_over_capacity_passes_backend_text() -> None:
    r = run(
        "create_reservation", {"table_id": 1, "slot_datetime": SLOT, "party_size": 4}, FakeBackend()
    )
    assert (
        code(r) == "backend_rejected" and r.error.message == "Party of 4 exceeds table capacity 2"
    )  # type: ignore[union-attr]
    assert r.writes == []


def test_cancel_within_two_hours_is_rejected_verbatim() -> None:
    b = FakeBackend()
    rid = b.add_reservation(1, 7, "2030-06-01T13:00:00")
    r = run("cancel_reservation", {"reservation_id": rid}, b)
    assert code(r) == "backend_rejected" and "within 2 hours" in r.error.message  # type: ignore[union-attr]


@pytest.mark.parametrize("name", ["cancel_reservation", "get_reservation_orders"])
def test_foreign_and_missing_reservations_look_identical(name: str) -> None:
    b = FakeBackend()
    foreign = b.add_reservation(2, 7, SLOT)
    a = run(name, {"reservation_id": foreign}, b)
    missing = run(name, {"reservation_id": 999}, b)
    assert code(a) == code(missing) == "not_permitted" and a.error == missing.error
    assert b.writes() == []


def test_add_items_partial_failure_reports_both_and_keeps_ledger() -> None:
    b = FakeBackend()
    rid = b.add_reservation(1, 7, SLOT)
    r = run(
        "add_order_items",
        {
            "reservation_id": rid,
            "items": [{"menu_item_id": 1, "quantity": 2}, {"menu_item_id": 999}],
        },
        b,
    )
    assert r.ok and len(r.data["added"]) == 1
    assert r.data["failed"] == [{"menu_item_id": 999, "reason": "Menu item not found"}]
    assert len(r.writes) == 1 and r.writes[0].action == "added"


def test_add_items_all_failed_is_an_error_with_reasons() -> None:
    b = FakeBackend()
    rid = b.add_reservation(1, 7, SLOT)
    r = run("add_order_items", {"reservation_id": rid, "items": [{"menu_item_id": 999}]}, b)
    assert not r.ok and r.data["failed"] and r.writes == []


def test_add_items_limits() -> None:
    b = FakeBackend()
    rid = b.add_reservation(1, 7, SLOT)
    eleven = [{"menu_item_id": 1}] * 11
    assert (
        code(run("add_order_items", {"reservation_id": rid, "items": eleven}, b))
        == "invalid_arguments"
    )
    assert (
        code(run("add_order_items", {"reservation_id": rid, "items": []}, b)) == "invalid_arguments"
    )


def test_get_orders_includes_names_and_remove_checks_ownership() -> None:
    b = FakeBackend()
    mine = b.add_reservation(1, 7, SLOT)
    theirs = b.add_reservation(2, 8, SLOT)
    run("add_order_items", {"reservation_id": mine, "items": [{"menu_item_id": 1}]}, b)
    run("add_order_items", {"reservation_id": theirs, "items": [{"menu_item_id": 2}]}, b, 2)
    orders = run("get_reservation_orders", {"reservation_id": mine}, b).data["orders"]
    assert orders[0]["name"] == "Paneer Tikka"
    assert code(run("remove_order_item", {"order_id": 2}, b)) == "not_permitted"
    assert 2 in b.orders  # untouched
    removed = run("remove_order_item", {"order_id": 1}, b)
    assert removed.ok and removed.writes[0].action == "removed" and 1 not in b.orders


def test_list_my_reservations_only_returns_own() -> None:
    b = FakeBackend()
    b.add_reservation(1, 7, SLOT)
    b.add_reservation(2, 8, SLOT)
    r = run("list_my_reservations", {}, b)
    assert [x["id"] for x in r.data["reservations"]] == [1]
