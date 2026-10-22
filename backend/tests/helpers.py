"""Small helpers shared by the API tests."""

import secrets
from typing import Any

from fastapi.testclient import TestClient

Json = dict[str, Any]

OUTLET = "JPR-013-7429"  # the outlet in the seed


def phone() -> str:
    """A fresh valid mobile number, so tests never share a customer."""
    return "9" + "".join(str(secrets.randbelow(10)) for _ in range(9))


def product_detail(client: TestClient, name: str) -> Json:
    found = [p for p in client.get("/products").json() if p["name"] == name]
    assert len(found) == 1, name
    body: Json = client.get(f"/products/{found[0]['id']}").json()
    return body


def choice(detail: Json, group: str, name: str) -> Json:
    for g in detail["option_groups"]:
        if g["name"] == group:
            return {"option_id": next(o["id"] for o in g["options"] if o["name"] == name)}
    raise AssertionError(group)


def new_order(client: TestClient, **extra: Any) -> int:
    response = client.post("/orders", json={"outlet": OUTLET, **extra})
    assert response.status_code == 201, response.text
    order_id: int = response.json()["id"]
    return order_id


def new_customer(client: TestClient, **extra: Any) -> int:
    response = client.post("/customers", json={"phone": phone(), **extra})
    assert response.status_code == 201, response.text
    customer_id: int = response.json()["id"]
    return customer_id


def add_line(client: TestClient, order_id: int, line: Json) -> Json:
    response = client.post(f"/orders/{order_id}/lines", json=line)
    assert response.status_code == 201, response.text
    body: Json = response.json()
    return body


def ketchup_line(detail: Json, **extra: Any) -> Json:
    """The simplest complete line for a burger: just the sauce answered."""
    return {
        "product_id": detail["id"],
        "options": [choice(detail, "Sauce", "Complimentary Ketchup")],
        **extra,
    }


def placed_order(client: TestClient, customer_id: int | None, *lines: Json) -> Json:
    """Start an order for the customer, add the lines and confirm it."""
    order_id = new_order(client, customer_id=customer_id) if customer_id else new_order(client)
    for line in lines:
        add_line(client, order_id, line)
    response = client.post(f"/orders/{order_id}/confirm")
    assert response.status_code == 200, response.text
    body: Json = response.json()
    return body
