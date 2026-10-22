from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.menu.models import Product, UnavailableProduct
from tests.helpers import (
    OUTLET,
    Json,
    add_line,
    choice,
    ketchup_line,
    new_customer,
    new_order,
    placed_order,
    product_detail,
)


@pytest.fixture
def mcspicy(client: TestClient) -> Json:
    return product_detail(client, "McSpicy® Chicken")


def burger(detail: Json, cheese: str | None = None, **extra: Any) -> Json:
    line = ketchup_line(detail, **extra)
    if cheese:
        line["options"].append(choice(detail, "Cheese", cheese))
    return line


def add(client: TestClient, order_id: int, line: Json) -> Json:
    return add_line(client, order_id, line)


def test_a_new_order_is_an_empty_draft(client: TestClient) -> None:
    order = client.get(f"/orders/{new_order(client)}").json()
    assert order["status"] == "draft" and order["lines"] == [] and order["confirmed_at"] is None
    assert order["customer_id"] is None and order["order_number"] is None
    assert (order["subtotal"], order["gst"], order["total"]) == (0, 0, 0)
    assert order["created_at"]


def test_unknown_outlet_and_order(client: TestClient) -> None:
    assert client.post("/orders", json={"outlet": "no-such-outlet"}).status_code == 404
    assert client.post("/orders", json={"outlet": OUTLET, "customer_id": 999999}).status_code == 404
    assert client.get("/orders/999999").status_code == 404
    assert client.post("/orders/999999/lines", json={"product_id": 1}).status_code == 404
    assert client.post("/orders/999999/confirm").status_code == 404


def test_adding_a_line_prices_it_and_keeps_the_choices(client: TestClient, mcspicy: Json) -> None:
    order_id = new_order(client)
    order = add(client, order_id, burger(mcspicy, "Double Cheese", note="no onions"))
    [line] = order["lines"]
    assert line["name"] == "McSpicy® Chicken" and line["note"] == "no onions"
    assert line["unit_price"] == line["line_total"] == 263.81
    assert {o["name"] for o in line["options"]} == {"Complimentary Ketchup", "Double Cheese"}
    assert (order["subtotal"], order["gst"], order["total"]) == (263.81, 13.19, 277.0)
    assert client.get(f"/orders/{order_id}").json() == order  # it was really saved


def test_several_lines_add_up_and_can_be_removed(client: TestClient, mcspicy: Json) -> None:
    order_id = new_order(client)
    add(client, order_id, burger(mcspicy))
    order = add(client, order_id, {**burger(mcspicy, "Cheese"), "quantity": 2})
    assert [x["line_total"] for x in order["lines"]] == [205.71, 468.56]
    assert order["subtotal"] == 674.27
    removed = client.delete(f"/orders/{order_id}/lines/{order['lines'][0]['id']}")
    assert removed.status_code == 200 and len(removed.json()["lines"]) == 1
    assert removed.json()["subtotal"] == 468.56


def test_removing_a_line_that_is_not_on_this_order(client: TestClient, mcspicy: Json) -> None:
    mine, other = new_order(client), new_order(client)
    their_line = add(client, other, burger(mcspicy))["lines"][0]["id"]
    assert client.delete(f"/orders/{mine}/lines/{their_line}").status_code == 404
    assert len(client.get(f"/orders/{other}").json()["lines"]) == 1  # untouched


def test_changing_a_quantity_keeps_the_line_and_reprices_the_order(
    client: TestClient, mcspicy: Json
) -> None:
    order_id = new_order(client)
    line = add(client, order_id, burger(mcspicy))["lines"][0]
    changed = client.patch(f"/orders/{order_id}/lines/{line['id']}", json={"quantity": 3})
    assert changed.status_code == 200
    [same] = changed.json()["lines"]
    assert same["id"] == line["id"] and same["quantity"] == 3
    assert same["unit_price"] == 205.71 and same["line_total"] == 617.13
    assert changed.json()["subtotal"] == 617.13
    assert client.get(f"/orders/{order_id}").json() == changed.json()  # it was really saved


def test_a_quantity_change_is_refused_for_bad_input_or_a_closed_order(
    client: TestClient, mcspicy: Json
) -> None:
    order_id, other = new_order(client), new_order(client)
    line = add(client, order_id, burger(mcspicy))["lines"][0]["id"]
    url = f"/orders/{order_id}/lines/{line}"
    assert client.patch(url, json={"quantity": 0}).status_code == 422
    assert client.patch(f"/orders/{other}/lines/{line}", json={"quantity": 2}).status_code == 404
    assert client.post(f"/orders/{order_id}/confirm").status_code == 200
    assert client.patch(url, json={"quantity": 2}).status_code == 409
    assert client.get(f"/orders/{order_id}").json()["lines"][0]["quantity"] == 1


def test_a_cancelled_draft_is_kept_but_closed(client: TestClient, mcspicy: Json) -> None:
    order_id = new_order(client)
    line = add(client, order_id, burger(mcspicy))["lines"][0]["id"]
    cancelled = client.delete(f"/orders/{order_id}")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert len(cancelled.json()["lines"]) == 1  # the record stays
    assert client.delete(f"/orders/{order_id}").status_code == 200  # repeating is harmless
    assert client.post(f"/orders/{order_id}/lines", json=burger(mcspicy)).status_code == 409
    assert client.delete(f"/orders/{order_id}/lines/{line}").status_code == 409
    assert client.patch(f"/orders/{order_id}/lines/{line}", json={"quantity": 2}).status_code == 409
    assert client.post(f"/orders/{order_id}/confirm").status_code == 409
    assert client.delete("/orders/999999").status_code == 404


def test_every_error_has_a_code_and_a_message(client: TestClient, mcspicy: Json) -> None:
    def detail(response: Any, status: int) -> Json:
        assert response.status_code == status
        body: Json = response.json()["detail"]
        assert set(body) >= {"code", "message"} and body["message"]
        return body

    assert detail(client.get("/orders/999999"), 404)["code"] == "not_found"
    assert detail(client.get("/products/999999"), 404)["code"] == "not_found"
    assert detail(client.get("/customers/999999"), 404)["code"] == "not_found"
    order_id = new_order(client)
    assert detail(client.post(f"/orders/{order_id}/confirm"), 409)["code"] == "empty_order"
    line = add(client, order_id, burger(mcspicy))["lines"][0]["id"]
    assert detail(client.delete(f"/orders/{order_id}/lines/999999"), 404)["code"] == "not_found"
    client.delete(f"/orders/{order_id}")
    assert detail(client.delete(f"/orders/{order_id}/lines/{line}"), 409)["code"] == "order_closed"
    incomplete = client.post(
        f"/orders/{new_order(client)}/lines",
        json={"product_id": mcspicy["id"], "meal_size": "Medium"},  # no side or drink chosen
    )
    assert detail(incomplete, 422)["code"] == "invalid_line"


def test_a_confirmed_order_cannot_be_cancelled(client: TestClient, mcspicy: Json) -> None:
    order = placed_order(client, None, burger(mcspicy))
    assert client.delete(f"/orders/{order['id']}").status_code == 409
    assert client.get(f"/orders/{order['id']}").json()["status"] == "confirmed"


def test_a_cancelled_cart_is_not_offered_back_to_the_customer(
    client: TestClient, mcspicy: Json
) -> None:
    customer = new_customer(client)
    order_id = new_order(client, customer_id=customer)
    add(client, order_id, burger(mcspicy))
    assert client.get(f"/customers/{customer}/draft").json()["id"] == order_id
    client.delete(f"/orders/{order_id}")
    assert client.get(f"/customers/{customer}/draft").status_code == 404
    assert client.get(f"/customers/{customer}/orders").json() == []


def test_an_incomplete_line_is_refused_and_nothing_is_saved(
    client: TestClient, mcspicy: Json
) -> None:
    order_id = new_order(client)
    line = {"product_id": mcspicy["id"], "meal_size": "Medium"}  # no side or drink chosen
    refused = client.post(f"/orders/{order_id}/lines", json=line)
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["problems"] == [] and "Meal side" in detail["missing"][0]["message"]
    assert client.get(f"/orders/{order_id}").json()["lines"] == []


def test_a_line_without_a_sauce_is_saved_with_the_default_and_can_be_confirmed(
    client: TestClient, mcspicy: Json
) -> None:
    order_id = new_order(client)
    saved = add(client, order_id, {"product_id": mcspicy["id"]})
    assert [o["name"] for o in saved["lines"][0]["options"]] == ["Complimentary Ketchup"]
    assert client.post(f"/orders/{order_id}/confirm").status_code == 200


def test_a_wrong_line_is_refused(client: TestClient, mcspicy: Json) -> None:
    order_id = new_order(client)
    line = {**burger(mcspicy), "meal_size": "Small"}
    refused = client.post(f"/orders/{order_id}/lines", json=line)
    assert refused.status_code == 422
    assert refused.json()["detail"]["problems"][0]["code"] == "no_such_meal"
    assert client.get(f"/orders/{order_id}").json()["lines"] == []


def test_confirming_freezes_the_order(client: TestClient, mcspicy: Json) -> None:
    order_id = new_order(client)
    add(client, order_id, burger(mcspicy, "Double Cheese"))
    placed = client.post(f"/orders/{order_id}/confirm")
    assert placed.status_code == 200
    body = placed.json()
    assert body["status"] == "confirmed" and body["confirmed_at"]
    assert (body["subtotal"], body["gst"], body["total"]) == (263.81, 13.19, 277.0)
    line_id = body["lines"][0]["id"]
    assert client.post(f"/orders/{order_id}/confirm").status_code == 409
    assert client.post(f"/orders/{order_id}/lines", json=burger(mcspicy)).status_code == 409
    assert client.delete(f"/orders/{order_id}/lines/{line_id}").status_code == 409
    assert client.get(f"/orders/{order_id}").json() == body


def test_an_empty_order_cannot_be_confirmed(client: TestClient) -> None:
    order_id = new_order(client)
    assert client.post(f"/orders/{order_id}/confirm").status_code == 409
    assert client.get(f"/orders/{order_id}").json()["status"] == "draft"


def test_a_placed_order_does_not_change_when_the_menu_does(
    client: TestClient, db: Session, mcspicy: Json
) -> None:
    order_id = new_order(client)
    add(client, order_id, burger(mcspicy))
    before = client.post(f"/orders/{order_id}/confirm").json()
    product = db.get(Product, mcspicy["id"])
    assert product is not None
    original = product.base_price
    product.base_price = Decimal("999.00")
    product.name = "Renamed"
    db.commit()
    try:
        assert client.get(f"/orders/{order_id}").json() == before
    finally:
        product.base_price = original
        product.name = "McSpicy® Chicken"
        db.commit()


def test_an_item_taken_off_before_confirming_blocks_it(
    client: TestClient, db: Session, mcspicy: Json
) -> None:
    order_id = new_order(client)
    add(client, order_id, burger(mcspicy))
    row = UnavailableProduct(outlet_id=1, product_id=mcspicy["id"])
    db.add(row)
    db.commit()
    try:
        refused = client.post(f"/orders/{order_id}/confirm")
        assert refused.status_code == 409
        assert refused.json()["detail"]["problems"][0]["code"] == "unavailable"
        assert client.get(f"/orders/{order_id}").json()["status"] == "draft"
    finally:
        db.delete(row)
        db.commit()
    assert client.post(f"/orders/{order_id}/confirm").status_code == 200


def test_a_price_change_is_shown_before_it_is_accepted(
    client: TestClient, db: Session, mcspicy: Json
) -> None:
    order_id = new_order(client)
    add(client, order_id, burger(mcspicy))
    product = db.get(Product, mcspicy["id"])
    assert product is not None
    original = product.base_price
    product.base_price = original + Decimal("10.00")
    db.commit()
    try:
        refused = client.post(f"/orders/{order_id}/confirm")
        assert refused.status_code == 409
        [issue] = refused.json()["detail"]["problems"]
        assert issue["code"] == "price_changed" and "215.71" in issue["message"]
        shown = client.get(f"/orders/{order_id}").json()
        assert shown["status"] == "draft" and shown["lines"][0]["unit_price"] == 215.71
        placed = client.post(f"/orders/{order_id}/confirm")  # the customer has now seen it
        assert placed.status_code == 200 and placed.json()["total"] == 226.5
    finally:
        product.base_price = original
        db.commit()


def test_an_order_shows_the_outlet_code_it_was_placed_at(client: TestClient) -> None:
    order_id = new_order(client)
    assert client.get(f"/orders/{order_id}").json()["outlet"] == OUTLET
