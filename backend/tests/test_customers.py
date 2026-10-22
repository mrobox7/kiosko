from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.menu.models import Outlet, Product
from app.orders.models import Order, OrderLine, OrderLineOption
from tests.helpers import (
    OUTLET,
    Json,
    add_line,
    ketchup_line,
    new_customer,
    new_order,
    phone,
    placed_order,
    product_detail,
)


@pytest.fixture
def mcspicy(client: TestClient) -> Json:
    return product_detail(client, "McSpicy® Chicken")


@pytest.fixture
def tikki(client: TestClient) -> Json:
    return product_detail(client, "McAloo Tikki Burger ®")


def test_a_new_number_creates_a_customer(client: TestClient) -> None:
    response = client.post("/customers", json={"phone": "98765 43210", "name": " Asha "})
    number = response.json()["phone"]
    assert response.status_code in (200, 201) and number == "+919876543210"
    assert response.json()["name"] == "Asha" and response.json()["preferences"] == {}
    fresh = client.post("/customers", json={"phone": phone()})
    assert fresh.status_code == 201 and fresh.json()["email"] is None


def test_the_same_number_finds_the_same_customer(client: TestClient) -> None:
    number = phone()
    first = client.post("/customers", json={"phone": number})
    assert first.status_code == 201
    for written in (number, f"+91 {number[:5]} {number[5:]}", f"0{number}", f"91{number}"):
        again = client.post("/customers", json={"phone": written})
        assert again.status_code == 200 and again.json()["id"] == first.json()["id"], written


def test_known_customers_get_missing_details_but_keep_existing_ones(client: TestClient) -> None:
    number = phone()
    client.post("/customers", json={"phone": number})
    filled = client.post("/customers", json={"phone": number, "name": "Ravi", "email": "R@X.com"})
    assert (filled.json()["name"], filled.json()["email"]) == ("Ravi", "r@x.com")
    other = client.post("/customers", json={"phone": number, "name": "Someone", "email": "o@x.com"})
    assert (other.json()["name"], other.json()["email"]) == ("Ravi", "r@x.com")


def test_bad_details_are_refused(client: TestClient) -> None:
    for bad in ["", "12345", "5876543210", "98765432101", "abcdefghij"]:
        assert client.post("/customers", json={"phone": bad}).status_code == 422, bad
    assert client.post("/customers", json={"phone": phone(), "email": "nope"}).status_code == 422
    assert client.post("/customers", json={}).status_code == 422
    blank = client.post("/customers", json={"phone": phone(), "name": "  ", "email": " "})
    assert blank.json()["name"] is None and blank.json()["email"] is None


def test_get_a_customer(client: TestClient) -> None:
    customer_id = new_customer(client, name="Meera")
    assert client.get(f"/customers/{customer_id}").json()["name"] == "Meera"
    assert client.get("/customers/999999").status_code == 404


def test_preferences_merge_key_by_key(client: TestClient) -> None:
    customer_id = new_customer(client)
    url = f"/customers/{customer_id}/preferences"
    client.patch(url, json={"preferences": {"diet": "veg"}})
    client.patch(url, json={"preferences": {"allergies": ["milk"]}})
    merged = client.patch(url, json={"preferences": {"diet": "vegan"}}).json()
    assert merged["preferences"] == {"diet": "vegan", "allergies": ["milk"]}
    assert client.get(f"/customers/{customer_id}").json()["preferences"] == merged["preferences"]
    assert (
        client.patch("/customers/999999/preferences", json={"preferences": {}}).status_code == 404
    )


def test_an_order_can_start_with_a_customer_or_get_one_later(client: TestClient) -> None:
    customer_id = new_customer(client)
    mine = client.post("/orders", json={"outlet": OUTLET, "customer_id": customer_id}).json()
    assert mine["customer_id"] == customer_id
    order_id = new_order(client)
    attached = client.put(f"/orders/{order_id}/customer", json={"customer_id": customer_id})
    assert attached.status_code == 200 and attached.json()["customer_id"] == customer_id
    assert (
        client.put(f"/orders/{order_id}/customer", json={"customer_id": 999999}).status_code == 404
    )
    assert (
        client.put("/orders/999999/customer", json={"customer_id": customer_id}).status_code == 404
    )


def test_a_placed_order_cannot_change_customer(client: TestClient, mcspicy: Json) -> None:
    placed = placed_order(client, None, ketchup_line(mcspicy))
    other = new_customer(client)
    response = client.put(f"/orders/{placed['id']}/customer", json={"customer_id": other})
    assert response.status_code == 409


def test_order_numbers_count_up_per_outlet_and_restart_each_day(
    client: TestClient, db: Session, mcspicy: Json
) -> None:
    draft = new_order(client)
    assert client.get(f"/orders/{draft}").json()["order_number"] is None
    add_line(client, draft, ketchup_line(mcspicy))
    first = client.post(f"/orders/{draft}/confirm").json()["order_number"]
    second = placed_order(client, None, ketchup_line(mcspicy))["order_number"]
    assert second == first + 1

    other_outlet = Outlet(code="test-outlet", name="Test outlet", address="Nowhere")
    db.add(other_outlet)
    db.commit()
    try:
        today = db.get(Order, draft)
        assert today is not None and today.business_date is not None
        db.add(
            Order(
                outlet_id=other_outlet.id,
                status="confirmed",
                order_number=41,
                business_date=today.business_date - timedelta(days=1),
                created_at=today.created_at,
                confirmed_at=today.confirmed_at,
                subtotal=Decimal(0),
                gst=Decimal(0),
                total=Decimal(0),
            )
        )
        db.commit()
        order_id = client.post("/orders", json={"outlet": other_outlet.code}).json()["id"]
        add_line(client, order_id, ketchup_line(mcspicy))
        assert client.post(f"/orders/{order_id}/confirm").json()["order_number"] == 1
    finally:
        db.query(OrderLineOption).filter(
            OrderLineOption.line_id.in_(
                db.query(OrderLine.id).join(Order).filter(Order.outlet_id == other_outlet.id)
            )
        ).delete(synchronize_session=False)
        db.query(OrderLine).filter(
            OrderLine.order_id.in_(db.query(Order.id).filter(Order.outlet_id == other_outlet.id))
        ).delete(synchronize_session=False)
        db.query(Order).filter(Order.outlet_id == other_outlet.id).delete()
        db.delete(other_outlet)
        db.commit()


def test_history_has_only_this_customers_confirmed_orders_newest_first(
    client: TestClient, mcspicy: Json, tikki: Json
) -> None:
    me, someone_else = new_customer(client), new_customer(client)
    older = placed_order(client, me, ketchup_line(mcspicy))
    newer = placed_order(client, me, ketchup_line(mcspicy), ketchup_line(tikki))
    placed_order(client, someone_else, ketchup_line(mcspicy))
    placed_order(client, None, ketchup_line(mcspicy))  # anonymous: nobody's history
    add_line(client, new_order(client, customer_id=me), ketchup_line(tikki))  # a draft: not history
    history = client.get(f"/customers/{me}/orders").json()
    assert [o["id"] for o in history] == [newer["id"], older["id"]]
    assert all(o["status"] == "confirmed" and o["customer_id"] == me for o in history)
    assert len(client.get(f"/customers/{me}/orders", params={"limit": 1}).json()) == 1
    assert client.get(f"/customers/{new_customer(client)}/orders").json() == []
    assert client.get("/customers/999999/orders").status_code == 404


def test_favourites_are_the_most_ordered_items(
    client: TestClient, db: Session, mcspicy: Json, tikki: Json
) -> None:
    me = new_customer(client)
    placed_order(client, me, ketchup_line(mcspicy, quantity=2), ketchup_line(tikki))
    placed_order(client, me, ketchup_line(mcspicy))
    add_line(client, new_order(client, customer_id=me), ketchup_line(tikki, quantity=9))  # a draft
    top = client.get(f"/customers/{me}/favourites").json()
    assert [f["name"] for f in top] == ["McSpicy® Chicken", "McAloo Tikki Burger ®"]
    assert (top[0]["total_quantity"], top[0]["times_ordered"]) == (3, 2)
    assert (top[1]["total_quantity"], top[1]["times_ordered"]) == (1, 1)
    assert top[0]["last_ordered_at"] and top[0]["product_id"] == mcspicy["id"]
    assert len(client.get(f"/customers/{me}/favourites", params={"limit": 1}).json()) == 1
    assert client.get(f"/customers/{new_customer(client)}/favourites").json() == []

    product = db.get(Product, tikki["id"])
    assert product is not None
    product.is_active = False
    db.commit()
    try:
        names = [f["name"] for f in client.get(f"/customers/{me}/favourites").json()]
        assert names == ["McSpicy® Chicken"]  # items taken off the menu are not suggested
    finally:
        product.is_active = True
        db.commit()


def test_an_unfinished_cart_can_be_resumed(client: TestClient, mcspicy: Json, tikki: Json) -> None:
    me = new_customer(client)
    assert client.get(f"/customers/{me}/draft").status_code == 404
    new_order(client, customer_id=me)  # empty carts do not count
    assert client.get(f"/customers/{me}/draft").status_code == 404
    first = new_order(client, customer_id=me)
    add_line(client, first, ketchup_line(mcspicy))
    assert client.get(f"/customers/{me}/draft").json()["id"] == first
    second = new_order(client, customer_id=me)
    add_line(client, second, ketchup_line(tikki))
    resumed = client.get(f"/customers/{me}/draft").json()
    assert resumed["id"] == second and resumed["lines"][0]["name"].startswith("McAloo")
    client.post(f"/orders/{second}/confirm")
    assert client.get(f"/customers/{me}/draft").json()["id"] == first  # placed carts are done
    assert client.get("/customers/999999/draft").status_code == 404
