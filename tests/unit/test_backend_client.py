import httpx
import pytest

from app.backend.client import BackendClient
from app.backend.errors import (
    BackendConflict,
    BackendNotFound,
    BackendRuleViolation,
    BackendUnavailable,
)
from app.backend.models import MenuFilters
from tests.support.fake_backend import FakeBackend


def client_for(handler) -> BackendClient:
    return BackendClient(httpx.Client(base_url="http://t", transport=httpx.MockTransport(handler)))


def test_get_menu_sends_filters_and_parses() -> None:
    fake = FakeBackend()
    items = fake.client.get_menu(
        MenuFilters(category="starter", tags_any=["vegetarian"], max_price=400)
    )
    assert items and all(i.category == "starter" and i.price <= 400 for i in items)
    params = fake.requests[0].url.params
    assert params["tags_any"] == "vegetarian" and params["available_only"] == "true"
    assert "exclude_tags" not in params


def test_repeated_list_params() -> None:
    fake = FakeBackend()
    fake.client.get_menu(MenuFilters(exclude_tags=["contains-nuts", "contains-dairy"]))
    assert fake.requests[0].url.params.get_list("exclude_tags") == [
        "contains-nuts",
        "contains-dairy",
    ]


@pytest.mark.parametrize(
    ("status", "exc"),
    [(404, BackendNotFound), (409, BackendConflict), (422, BackendRuleViolation)],
)
def test_status_mapping_keeps_message(status: int, exc: type[Exception]) -> None:
    c = client_for(lambda r: httpx.Response(status, json={"detail": "nope"}))
    with pytest.raises(exc, match="nope"):
        c.get_menu()


def test_5xx_is_unavailable_and_maybe_processed() -> None:
    c = client_for(lambda r: httpx.Response(503, text="down"))
    with pytest.raises(BackendUnavailable) as info:
        c.get_menu()
    assert info.value.may_have_been_processed


def test_connection_error_not_processed() -> None:
    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(BackendUnavailable) as info:
        client_for(boom).get_menu()
    assert not info.value.may_have_been_processed


def test_read_timeout_maybe_processed() -> None:
    def slow(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(BackendUnavailable) as info:
        client_for(slow).get_menu()
    assert info.value.may_have_been_processed


def test_new_calls_hit_the_right_endpoints_and_parse() -> None:
    from datetime import datetime

    fake = FakeBackend()
    slot = datetime(2030, 6, 10, 19, 30)
    assert fake.client.get_availability(slot, 4, "outdoor").available_tables
    r = fake.client.create_reservation(1, 7, slot, 4)
    assert fake.client.get_reservation(r.id).slot_datetime == slot
    order = fake.client.add_order(r.id, 1, 2)
    assert fake.client.list_reservation_orders(r.id) == [order]
    assert fake.client.list_customer_orders(1) == [order]
    assert fake.client.delete_order(order.id) is None
    assert fake.client.list_customer_reservations(1, "confirmed")[0].id == r.id
    assert fake.client.cancel_reservation(r.id).status == "cancelled"
    sent = [(q.method, q.url.path) for q in fake.requests]
    assert ("POST", "/reservations") in sent and ("DELETE", "/orders/1") in sent


def test_conflict_on_double_booking() -> None:
    from datetime import datetime

    fake = FakeBackend()
    slot = datetime(2030, 6, 10, 19, 30)
    fake.client.create_reservation(1, 7, slot, 4)
    with pytest.raises(BackendConflict, match="already booked"):
        fake.client.create_reservation(2, 7, slot, 4)
