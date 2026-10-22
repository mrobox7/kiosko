import json

import httpx
import pytest

from app.backend.client import BackendClient
from app.backend.errors import (
    BackendConflict,
    BackendNotFound,
    BackendRuleViolation,
    BackendUnavailable,
)


def client_for(handler) -> BackendClient:
    return BackendClient(httpx.Client(base_url="http://t", transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize(
    ("status", "exc"),
    [(404, BackendNotFound), (409, BackendConflict), (422, BackendRuleViolation)],
)
def test_status_mapping_keeps_message(status: int, exc: type[Exception]) -> None:
    c = client_for(lambda r: httpx.Response(status, json={"detail": "nope"}))
    with pytest.raises(exc, match="nope"):
        c.get_order(1)


def test_5xx_is_unavailable_and_maybe_processed() -> None:
    c = client_for(lambda r: httpx.Response(503, text="down"))
    with pytest.raises(BackendUnavailable) as info:
        c.get_order(1)
    assert info.value.may_have_been_processed


def test_connection_error_not_processed() -> None:
    def boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(BackendUnavailable) as info:
        client_for(boom).get_order(1)
    assert not info.value.may_have_been_processed


def test_read_timeout_maybe_processed() -> None:
    def slow(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(BackendUnavailable) as info:
        client_for(slow).get_order(1)
    assert info.value.may_have_been_processed


def _refused(status: int, detail: object) -> BackendClient:
    return client_for(lambda r: httpx.Response(status, json={"detail": detail}))


def test_a_cart_refusal_keeps_the_codes_and_reads_as_one_sentence() -> None:
    need = {"line": 0, "code": "required", "message": "Burger: Sauce still needs 1 choice"}
    detail = {"code": "invalid_line", "message": "The item is incomplete", "missing": [need]}
    with pytest.raises(BackendRuleViolation) as info:
        _refused(422, detail).add_order_line(7, {"product_id": 5})
    error = info.value
    assert error.code == "invalid_line" and error.missing == [need] and error.problems == []
    assert error.message == "The item is incomplete: Burger: Sauce still needs 1 choice"


def test_a_plain_refusal_has_a_code_and_just_its_message() -> None:
    with pytest.raises(BackendNotFound) as info:
        _refused(404, {"code": "not_found", "message": "No order 99"}).get_order(99)
    assert (info.value.code, info.value.message) == ("not_found", "No order 99")
    assert info.value.missing == [] and info.value.problems == []


def test_errors_in_other_shapes_pass_through_as_text() -> None:
    fields = [{"loc": ["body", "quantity"], "msg": "too small"}]
    with pytest.raises(BackendRuleViolation) as info:
        _refused(422, fields).set_line_quantity(7, 10, 0)
    assert info.value.code is None and "too small" in info.value.message
    with pytest.raises(BackendConflict) as plain:
        _refused(409, "old style").cancel_order(7)
    assert plain.value.code is None and plain.value.message == "old style"
    with pytest.raises(BackendRuleViolation, match="HTTP 422"):
        client_for(lambda r: httpx.Response(422)).get_order(7)


def test_the_order_calls_use_the_right_paths_and_bodies() -> None:
    from tests.support.fake_order_server import FakeOrderServer

    server = FakeOrderServer()
    http = httpx.Client(base_url="http://t", transport=httpx.MockTransport(server.handle))
    backend = BackendClient(http)
    backend.create_order("JPR-013-7429", customer_id=3)
    assert server.created_with == {"outlet": "JPR-013-7429", "customer_id": 3}
    backend.create_order("JPR-013-7429")
    assert server.created_with == {"outlet": "JPR-013-7429"}  # no customer: the key is left out
    backend.add_order_line(7, {"product_id": 4, "quantity": 1, "meal_size": None, "note": None,
                               "options": [{"option_id": 1, "qty": 1}]})  # fmt: skip
    [line] = backend.get_order(7).lines
    changed = backend.set_line_quantity(7, line.id, 3)
    assert changed.lines[0].quantity == 3 and changed.lines[0].id == line.id
    assert backend.attach_customer(7, 9).customer_id == 9
    assert backend.cancel_order(7).status == "cancelled"
    assert backend.cancel_order(7).status == "cancelled"  # repeating is fine
    sent = [(m, p) for m, p in server.requests]
    assert ("PATCH", f"/orders/7/lines/{line.id}") in sent
    assert ("PUT", "/orders/7/customer") in sent and ("DELETE", "/orders/7") in sent


def test_a_placed_order_cannot_be_cancelled() -> None:
    from tests.support.fake_order_server import FakeOrderServer

    server = FakeOrderServer()
    server.lines = [{"id": 1, "name": "x", "quantity": 1, "line_total": 10.0, "options": []}]
    backend = BackendClient(
        httpx.Client(base_url="http://t", transport=httpx.MockTransport(server.handle))
    )
    backend.confirm_order(7)
    with pytest.raises(BackendConflict) as info:
        backend.cancel_order(7)
    assert info.value.code == "order_closed"


def test_customers_are_found_or_added_by_phone_alone() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            body = {"id": 3, "phone": "+919876543210", "name": None, "email": None,
                    "preferences": {}, "created_at": "2026-10-21T10:00:00Z"}  # fmt: skip
            return httpx.Response(201, json=body)
        favourite = {"product_id": 5, "name": "McSpicy", "times_ordered": 4, "total_quantity": 6,
                     "last_ordered_at": "2026-10-20T10:00:00Z"}  # fmt: skip
        return httpx.Response(200, json=[favourite])

    backend = client_for(handler)
    customer = backend.find_or_add_customer("98765 43210")
    assert customer.id == 3 and customer.name is None  # no name is fine
    assert json.loads(seen[0].content) == {"phone": "98765 43210"}  # the server cleans the number
    [usual] = backend.get_favourites(3, limit=2)
    assert (usual.name, usual.times_ordered) == ("McSpicy", 4)
    assert seen[1].url.path == "/customers/3/favourites" and seen[1].url.params["limit"] == "2"


def test_the_outlet_is_read_by_its_code() -> None:
    body = {"code": "JPR-013-7429", "name": "McDonald's Nemi Nagar", "address": "Gandhi Path West"}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    outlet = client_for(handler).get_outlet("JPR-013-7429")
    assert (outlet.name, outlet.address) == ("McDonald's Nemi Nagar", "Gandhi Path West")
    assert seen[0].url.path == "/outlets/JPR-013-7429"
