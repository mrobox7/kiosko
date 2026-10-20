from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models

Json = dict[str, Any]
PHONE = "9876543210"


def new_order(client: TestClient, **extra: Any) -> int:
    response = client.post("/orders", json={"outlet_id": 1, "phone": PHONE, **extra})
    assert response.status_code == 201, response.text
    order_id: int = response.json()["id"]
    return order_id


@pytest.fixture
def mcspicy(client: TestClient) -> Json:
    found = [p for p in client.get("/products").json() if p["name"] == "McSpicy® Chicken"]
    body: Json = client.get(f"/products/{found[0]['id']}").json()
    return body


def choice(detail: Json, group: str, name: str) -> Json:
    for g in detail["option_groups"]:
        if g["name"] == group:
            return {"option_id": next(o["id"] for o in g["options"] if o["name"] == name)}
    raise AssertionError(group)


def burger(detail: Json, cheese: str | None = None, **extra: Any) -> Json:
    options = [choice(detail, "Sauce", "Complimentary Ketchup")]
    if cheese:
        options.append(choice(detail, "Cheese", cheese))
    return {"product_id": detail["id"], "options": options, **extra}


def add(client: TestClient, order_id: int, line: Json) -> Json:
    response = client.post(f"/orders/{order_id}/lines", json=line)
    assert response.status_code == 201, response.text
    body: Json = response.json()
    return body


def test_phone_is_normalised(client: TestClient) -> None:
    for written in ["9876543210", "+91 98765 43210", "09876543210", "98765-43210", "919876543210"]:
        response = client.post("/orders", json={"outlet_id": 1, "phone": written})
        assert response.status_code == 201 and response.json()["phone"] == "+919876543210", written


def test_a_bad_phone_or_email_is_refused(client: TestClient) -> None:
    for phone in ["", "12345", "5876543210", "98765432101", "abcdefghij"]:
        assert client.post("/orders", json={"outlet_id": 1, "phone": phone}).status_code == 422
    bad_email = {"outlet_id": 1, "phone": PHONE, "email": "not-an-email"}
    assert client.post("/orders", json=bad_email).status_code == 422
    assert client.post("/orders", json={"outlet_id": 1}).status_code == 422  # phone is required


def test_email_is_optional_and_tidied(client: TestClient) -> None:
    plain = client.post("/orders", json={"outlet_id": 1, "phone": PHONE}).json()
    assert plain["email"] is None
    blank = client.post("/orders", json={"outlet_id": 1, "phone": PHONE, "email": "  "}).json()
    assert blank["email"] is None
    given = client.post("/orders", json={"outlet_id": 1, "phone": PHONE, "email": " Me@Mail.COM "})
    assert given.json()["email"] == "me@mail.com"


def test_a_new_order_is_an_empty_draft(client: TestClient) -> None:
    order = client.get(f"/orders/{new_order(client)}").json()
    assert order["status"] == "draft" and order["lines"] == [] and order["confirmed_at"] is None
    assert (order["subtotal"], order["gst"], order["total"]) == (0, 0, 0)
    assert order["created_at"]


def test_unknown_outlet_and_order(client: TestClient) -> None:
    assert client.post("/orders", json={"outlet_id": 99, "phone": PHONE}).status_code == 404
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


def test_an_incomplete_line_is_refused_and_nothing_is_saved(
    client: TestClient, mcspicy: Json
) -> None:
    order_id = new_order(client)
    refused = client.post(f"/orders/{order_id}/lines", json={"product_id": mcspicy["id"]})
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["problems"] == [] and "Sauce" in detail["missing"][0]["message"]
    assert client.get(f"/orders/{order_id}").json()["lines"] == []


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
    product = db.get(models.Product, mcspicy["id"])
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
    row = models.OutletProduct(outlet_id=1, product_id=mcspicy["id"], available=False)
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
    product = db.get(models.Product, mcspicy["id"])
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
