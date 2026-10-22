from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.menu.models import Product, UnavailableProduct
from app.orders.pricing import gst
from tests.helpers import OUTLET

Json = dict[str, Any]


def detail(client: TestClient, name: str) -> Json:
    found = [p for p in client.get("/products").json() if p["name"] == name]
    assert len(found) == 1, name
    body: Json = client.get(f"/products/{found[0]['id']}").json()
    return body


def option(source: Json, group: str, name: str) -> int:
    for g in source["option_groups"]:
        if g["name"] == group:
            found: int = next(o["id"] for o in g["options"] if o["name"] == name)
            return found
    raise AssertionError(group)


def meal_option(source: Json, size: str, part: str, index: int = 0) -> Json:
    offer = next(m for m in source["meal_offers"] if m["size"] == size)
    chosen: Json = offer[part]["options"][index]
    return chosen


def price(client: TestClient, *lines: Json, outlet: str = OUTLET) -> Json:
    response = client.post("/orders/price", json={"outlet": outlet, "lines": list(lines)})
    assert response.status_code == 200, response.text
    body: Json = response.json()
    return body


def pick(option_id: int, qty: int = 1) -> Json:
    return {"option_id": option_id, "qty": qty}


@pytest.fixture
def mcspicy(client: TestClient) -> Json:
    return detail(client, "McSpicy® Chicken")


def test_the_worked_example_from_the_doc(client: TestClient, mcspicy: Json) -> None:
    cart = price(
        client,
        {
            "product_id": mcspicy["id"],
            "options": [
                pick(option(mcspicy, "Sauce", "Complimentary Ketchup")),
                pick(option(mcspicy, "Cheese", "Double Cheese")),
            ],
        },
    )
    assert cart["ready"] is True and cart["missing"] == [] and cart["problems"] == []
    line = cart["lines"][0]
    assert (line["base_price"], line["options_price"]) == (205.71, 58.1)
    assert line["unit_price"] == line["line_total"] == 263.81
    assert (cart["subtotal"], cart["gst"], cart["total"]) == (263.81, 13.19, 277.0)


def test_quantity_multiplies_the_line_not_the_unit(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    cart = price(client, {"product_id": mcspicy["id"], "quantity": 3, "options": [ketchup]})
    line = cart["lines"][0]
    assert line["unit_price"] == 205.71 and line["line_total"] == 617.13
    assert cart["subtotal"] == 617.13


def test_option_quantity_counts_each_time(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    cheese = pick(option(mcspicy, "Cheese", "Cheese"), qty=2)
    cart = price(client, {"product_id": mcspicy["id"], "options": [ketchup, cheese]})
    assert cart["ready"] is True
    assert cart["lines"][0]["options_price"] == 57.14  # 2 x 28.57
    again = price(
        client,
        {
            "product_id": mcspicy["id"],
            "options": [ketchup, pick(cheese["option_id"]), pick(cheese["option_id"])],
        },
    )
    assert again["lines"][0]["options_price"] == 57.14  # the same option listed twice


def test_two_lines_add_up_and_gst_is_rounded_once(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    line = {"product_id": mcspicy["id"], "options": [ketchup]}
    cart = price(client, line, line)
    assert [entry["index"] for entry in cart["lines"]] == [0, 1]
    assert cart["subtotal"] == 411.42 and cart["gst"] == 20.57 and cart["total"] == 431.99


def test_gst_rounds_half_up_to_the_paisa() -> None:
    assert gst(Decimal("100")) == Decimal("5.00")
    assert gst(Decimal("263.81")) == Decimal("13.19")  # 13.1905
    assert gst(Decimal("0.10")) == Decimal("0.01")  # 0.005 rounds up
    assert gst(Decimal("0")) == Decimal("0.00")


def test_a_required_question_left_open_is_reported_as_missing(
    client: TestClient, mcspicy: Json
) -> None:
    # A medium meal asks for a side and a drink, and neither has a default.
    cart = price(client, {"product_id": mcspicy["id"], "meal_size": "Medium"})
    assert cart["ready"] is False and cart["problems"] == []
    assert [m["code"] for m in cart["missing"]] == ["required", "required"]
    assert "Meal side" in cart["missing"][0]["message"] and cart["missing"][0]["line"] == 0
    assert cart["lines"][0]["meal_price"] > 0  # still priced with what it has


def test_an_unanswered_sauce_takes_its_default_ketchup(client: TestClient, mcspicy: Json) -> None:
    cart = price(client, {"product_id": mcspicy["id"]})
    assert cart["ready"] is True and cart["missing"] == [] and cart["problems"] == []
    [chosen] = cart["lines"][0]["options"]
    assert chosen["name"] == "Complimentary Ketchup" and chosen["group"] == "Sauce"
    assert cart["lines"][0]["unit_price"] == 205.71  # ketchup is free


def test_an_answer_given_replaces_the_default(client: TestClient, mcspicy: Json) -> None:
    no_ketchup = pick(option(mcspicy, "Sauce", "No Ketchup"))
    cart = price(client, {"product_id": mcspicy["id"], "options": [no_ketchup]})
    assert cart["ready"] is True
    assert [o["name"] for o in cart["lines"][0]["options"]] == ["No Ketchup"]


def test_a_default_that_is_not_on_sale_is_not_used(client: TestClient, mcspicy: Json) -> None:
    ketchup = option(mcspicy, "Sauce", "Complimentary Ketchup")
    base = f"/outlets/{OUTLET}/unavailable/options/{ketchup}"
    try:
        assert client.put(base).status_code == 204
        cart = price(client, {"product_id": mcspicy["id"]})
    finally:
        assert client.delete(base).status_code == 204  # the test database is shared
    assert cart["ready"] is False
    assert cart["missing"][0]["code"] == "required" and "Sauce" in cart["missing"][0]["message"]


def test_more_picks_than_allowed_is_a_problem(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    cart = price(
        client,
        {
            "product_id": mcspicy["id"],
            "options": [ketchup, pick(option(mcspicy, "Cheese", "Cheese"), 6)],
        },
    )
    assert cart["ready"] is False
    assert [p["code"] for p in cart["problems"]] == ["too_many"]
    cart = price(
        client,
        {
            "product_id": mcspicy["id"],
            "options": [ketchup, pick(option(mcspicy, "Sauce", "No Ketchup"))],
        },
    )
    assert [p["code"] for p in cart["problems"]] == ["too_many"]  # Sauce allows exactly 1


def test_an_option_from_another_product_is_refused(client: TestClient, mcspicy: Json) -> None:
    tikki = detail(client, "McAloo Tikki Burger ®")
    foreign = next(
        o["id"]
        for g in tikki["option_groups"]
        for o in g["options"]
        if o["id"] not in {x["id"] for gg in mcspicy["option_groups"] for x in gg["options"]}
    )
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    cart = price(client, {"product_id": mcspicy["id"], "options": [ketchup, pick(foreign)]})
    assert [p["code"] for p in cart["problems"]] == ["unknown_option"]
    assert (
        price(client, {"product_id": mcspicy["id"], "options": [pick(999999)]})["problems"][0][
            "code"
        ]
        == "unknown_option"
    )


def test_a_medium_meal_needs_a_side_and_a_drink(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    bare = price(client, {"product_id": mcspicy["id"], "meal_size": "Medium", "options": [ketchup]})
    assert bare["ready"] is False
    assert sorted(m["message"].split(": ")[1].split(" still")[0] for m in bare["missing"]) == [
        "Meal drink (Medium)",
        "Meal side (Medium)",
    ]
    side, drink = meal_option(mcspicy, "Medium", "side"), meal_option(mcspicy, "Medium", "drink")
    cart = price(
        client,
        {
            "product_id": mcspicy["id"],
            "meal_size": "Medium",
            "options": [ketchup, pick(side["id"]), pick(drink["id"])],
        },
    )
    assert cart["ready"] is True
    meal = next(m for m in mcspicy["meal_offers"] if m["size"] == "Medium")
    expected = (
        Decimal("205.71")
        + Decimal(str(meal["price_delta"]))
        + Decimal(str(side["price_delta"]))
        + Decimal(str(drink["price_delta"]))
    )
    line = cart["lines"][0]
    assert Decimal(str(line["unit_price"])) == expected
    assert line["meal_size"] == "Medium" and line["meal_price"] == meal["price_delta"]


def test_a_large_meal_needs_only_a_drink(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    large = {"product_id": mcspicy["id"], "meal_size": "Large"}
    bare = price(client, {**large, "options": [ketchup]})
    assert [m["message"].split(": ")[1].split(" still")[0] for m in bare["missing"]] == [
        "Meal drink (Large)"
    ]
    drink = meal_option(mcspicy, "Large", "drink")
    assert price(client, {**large, "options": [ketchup, pick(drink["id"])]})["ready"] is True


def test_a_meal_drink_is_refused_without_the_meal(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    drink = meal_option(mcspicy, "Medium", "drink")
    cart = price(client, {"product_id": mcspicy["id"], "options": [ketchup, pick(drink["id"])]})
    assert [p["code"] for p in cart["problems"]] == ["unknown_option"]


def test_a_meal_size_the_product_does_not_have(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    cart = price(client, {"product_id": mcspicy["id"], "meal_size": "Small", "options": [ketchup]})
    assert [p["code"] for p in cart["problems"]] == ["no_such_meal"]
    assert cart["lines"][0]["meal_price"] == 0 and cart["lines"][0]["meal_size"] is None


def test_a_combo_reports_its_choose_steps(client: TestClient) -> None:
    combo = detail(client, "McVeggie/McChicken(Any Two)+1 Medium Fries+2 McPuff")
    cart = price(client, {"product_id": combo["id"]})
    assert any("Burger choice" in m["message"] for m in cart["missing"])
    assert cart["lines"][0]["unit_price"] == combo["base_price"]


def test_unknown_and_hidden_products_are_not_priced(client: TestClient, db: Session) -> None:
    cart = price(client, {"product_id": 999999})
    assert cart["ready"] is False and cart["lines"] == []
    assert [p["code"] for p in cart["problems"]] == ["not_on_menu"]
    assert (cart["subtotal"], cart["gst"], cart["total"]) == (0, 0, 0)
    product = db.get(Product, 1)
    assert product is not None
    product.is_active = False
    db.commit()
    try:
        assert price(client, {"product_id": 1})["problems"][0]["code"] == "not_on_menu"
    finally:
        product.is_active = True
        db.commit()


def test_a_good_line_is_priced_next_to_a_bad_one(client: TestClient, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    cart = price(
        client, {"product_id": 999999}, {"product_id": mcspicy["id"], "options": [ketchup]}
    )
    assert [entry["index"] for entry in cart["lines"]] == [1]
    assert cart["problems"][0]["line"] == 0 and cart["subtotal"] == 205.71


def test_outlet_unavailable(client: TestClient, db: Session, mcspicy: Json) -> None:
    ketchup = pick(option(mcspicy, "Sauce", "Complimentary Ketchup"))
    line = {"product_id": mcspicy["id"], "options": [ketchup]}
    row = UnavailableProduct(outlet_id=1, product_id=mcspicy["id"])
    db.add(row)
    db.commit()
    try:
        cart = price(client, line)
        assert cart["lines"] == [] and cart["problems"][0]["code"] == "unavailable"
    finally:
        db.delete(row)
        db.commit()
    assert price(client, line)["lines"][0]["unit_price"] == 205.71


def test_bad_requests_are_rejected(client: TestClient, mcspicy: Json) -> None:
    line = {"product_id": mcspicy["id"]}
    assert (
        client.post("/orders/price", json={"outlet": "no-such-outlet", "lines": [line]}).status_code
        == 404
    )
    assert client.post("/orders/price", json={"outlet": OUTLET, "lines": []}).status_code == 422
    assert (
        client.post(
            "/orders/price", json={"outlet": OUTLET, "lines": [{**line, "quantity": 0}]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/orders/price", json={"outlet": OUTLET, "lines": [{**line, "options": [pick(1, 0)]}]}
        ).status_code
        == 422
    )
