"""What an outlet sells: products and options it has switched off, and what follows from that."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.menu.models import UnavailableOption, UnavailableProduct
from tests.helpers import OUTLET, Json, add_line, choice, ketchup_line, new_order, product_detail

OUTLET_ID = 1


@contextmanager
def switched_off(
    db: Session, *, products: tuple[int, ...] = (), options: tuple[int, ...] = ()
) -> Iterator[None]:
    rows: list[Any] = [UnavailableProduct(outlet_id=OUTLET_ID, product_id=p) for p in products]
    rows += [UnavailableOption(outlet_id=OUTLET_ID, option_id=o) for o in options]
    db.add_all(rows)
    db.commit()
    try:
        yield
    finally:
        for row in rows:
            db.delete(row)
        db.commit()


def menu(client: TestClient, path: str, outlet: bool = True) -> Any:
    return client.get(path, params={"outlet": OUTLET} if outlet else {})


def option_ids(detail: Json, group: str) -> list[int]:
    return [o["id"] for g in detail["option_groups"] if g["name"] == group for o in g["options"]]


def price(client: TestClient, line: Json) -> Json:
    body: Json = client.post("/orders/price", json={"outlet": OUTLET, "lines": [line]}).json()
    return body


# --- an option the outlet does not offer


def test_an_option_switched_off_is_left_out_and_refused(client: TestClient, db: Session) -> None:
    mcspicy = product_detail(client, "McSpicy® Chicken")
    ketchup = choice(mcspicy, "Sauce", "Complimentary Ketchup")["option_id"]
    with switched_off(db, options=(ketchup,)):
        ours = menu(client, f"/products/{mcspicy['id']}").json()
        assert ketchup not in option_ids(ours, "Sauce") and option_ids(ours, "Sauce")
        assert ketchup in option_ids(
            menu(client, f"/products/{mcspicy['id']}", False).json(), "Sauce"
        )

        cart = price(client, {"product_id": mcspicy["id"], "options": [{"option_id": ketchup}]})
        assert [p["code"] for p in cart["problems"]] == ["unavailable"]
        assert not cart["ready"]

        other = next(i for i in option_ids(ours, "Sauce"))
        assert price(client, {"product_id": mcspicy["id"], "options": [{"option_id": other}]})[
            "ready"
        ]
    assert ketchup in option_ids(menu(client, f"/products/{mcspicy['id']}").json(), "Sauce")


def test_a_choice_made_earlier_is_checked_again_when_placing_the_order(
    client: TestClient, db: Session
) -> None:
    mcspicy = product_detail(client, "McSpicy® Chicken")
    ketchup = choice(mcspicy, "Sauce", "Complimentary Ketchup")["option_id"]
    order_id = new_order(client)
    add_line(client, order_id, ketchup_line(mcspicy))
    with switched_off(db, options=(ketchup,)):
        refused = client.post(f"/orders/{order_id}/confirm")
        assert refused.status_code == 409
        assert refused.json()["detail"]["problems"][0]["code"] == "unavailable"
    assert client.post(f"/orders/{order_id}/confirm").status_code == 200


# --- a combo's burger choice that is itself a product

COMBO = "Spicy Paneer/Spicy Chicken Wrap(Any 2)+1 Med. Fries+2 Puff"
CHICKEN_WRAP = "Big Spicy Chicken Wrap"
PANEER_WRAP = "Big Spicy Paneer Wrap"


def wrap_ids(client: TestClient) -> tuple[Json, int, int, int]:
    combo = product_detail(client, COMBO)
    group = next(g for g in combo["option_groups"] if g["name"] == "Wrap choice")
    chicken = next(o for o in group["options"] if o["name"] == CHICKEN_WRAP)
    paneer = next(o for o in group["options"] if o["name"] == PANEER_WRAP)
    return combo, chicken["id"], paneer["id"], chicken["linked_product_id"]


def test_a_combo_choice_goes_when_its_product_is_switched_off(
    client: TestClient, db: Session
) -> None:
    combo, chicken_option, paneer_option, chicken_product = wrap_ids(client)
    with switched_off(db, products=(chicken_product,)):
        ours = menu(client, f"/products/{combo['id']}").json()
        assert option_ids(ours, "Wrap choice") == [paneer_option]

        refused = price(
            client, {"product_id": combo["id"], "options": [{"option_id": chicken_option}]}
        )
        assert [p["code"] for p in refused["problems"]] == ["unavailable"]
        accepted = price(
            client, {"product_id": combo["id"], "options": [{"option_id": paneer_option}]}
        )
        assert not accepted["problems"]
    assert chicken_option in option_ids(
        menu(client, f"/products/{combo['id']}").json(), "Wrap choice"
    )


def test_a_combo_with_no_choice_left_is_not_sold(client: TestClient, db: Session) -> None:
    combo, _, _, chicken_product = wrap_ids(client)
    paneer_product = next(
        p["id"] for p in client.get("/products").json() if p["name"] == PANEER_WRAP
    )
    with switched_off(db, products=(chicken_product, paneer_product)):
        assert menu(client, f"/products/{combo['id']}").status_code == 404
        assert combo["id"] not in {p["id"] for p in menu(client, "/products").json()}
        assert combo["id"] not in {p["id"] for p in menu(client, "/catalog").json()["products"]}
        assert combo["id"] in {p["id"] for p in menu(client, "/products", False).json()}

        cart = price(client, {"product_id": combo["id"]})
        assert cart["lines"] == [] and cart["problems"][0]["code"] == "unavailable"
    assert menu(client, f"/products/{combo['id']}").status_code == 200


# --- a meal upgrade whose drink or side is gone


def test_a_meal_is_dropped_when_its_drink_question_cannot_be_answered(
    client: TestClient, db: Session
) -> None:
    mcspicy = product_detail(client, "McSpicy® Chicken")
    offer = mcspicy["meal_offers"][0]
    drinks = tuple(o["id"] for o in offer["drink"]["options"])
    with switched_off(db, options=drinks):
        ours = menu(client, f"/products/{mcspicy['id']}").json()
        assert offer["size"] not in {m["size"] for m in ours["meal_offers"]}

        line = {**ketchup_line(mcspicy), "meal_size": offer["size"]}
        cart = price(client, line)
        assert cart["problems"] and cart["problems"][0]["code"] == "unavailable"
    ours = menu(client, f"/products/{mcspicy['id']}").json()
    assert offer["size"] in {m["size"] for m in ours["meal_offers"]}


# --- nothing is switched off


def test_without_an_outlet_nothing_is_hidden_even_if_switched_off_there(
    client: TestClient, db: Session
) -> None:
    combo, _, _, chicken_product = wrap_ids(client)
    everything = len(menu(client, "/products", False).json())
    with switched_off(db, products=(chicken_product,)):
        assert len(menu(client, "/products", False).json()) == everything
        assert len(menu(client, "/products").json()) == everything - 1


def test_the_pos_can_switch_a_product_off_and_on(client: TestClient, db: Session) -> None:
    detail = product_detail(client, "McSpicy® Chicken")
    base = f"/outlets/{OUTLET}/unavailable"
    try:
        assert client.put(f"{base}/products/{detail['id']}").status_code == 204
        assert client.put(f"{base}/products/{detail['id']}").status_code == 204  # harmless twice
        assert client.get(base).json() == {"products": [detail["id"]], "options": []}
        assert menu(client, f"/products/{detail['id']}").status_code == 404
    finally:
        assert client.delete(f"{base}/products/{detail['id']}").status_code == 204
    assert client.get(base).json() == {"products": [], "options": []}
    assert menu(client, f"/products/{detail['id']}").status_code == 200


def test_the_pos_can_switch_an_option_off_and_on(client: TestClient, db: Session) -> None:
    detail = product_detail(client, "McSpicy® Chicken")
    ketchup = choice(detail, "Sauce", "Complimentary Ketchup")["option_id"]
    base = f"/outlets/{OUTLET}/unavailable/options/{ketchup}"
    try:
        assert client.put(base).status_code == 204
        assert ketchup not in option_ids(menu(client, f"/products/{detail['id']}").json(), "Sauce")
    finally:
        assert client.delete(base).status_code == 204
    assert ketchup in option_ids(menu(client, f"/products/{detail['id']}").json(), "Sauce")


def test_switching_needs_a_known_outlet_and_item(client: TestClient) -> None:
    assert client.get("/outlets/nope/unavailable").status_code == 404
    assert client.put("/outlets/nope/unavailable/products/1").status_code == 404
    assert client.put(f"/outlets/{OUTLET}/unavailable/products/999999").status_code == 404
    assert client.put(f"/outlets/{OUTLET}/unavailable/options/999999").status_code == 404
    assert client.delete(f"/outlets/{OUTLET}/unavailable/options/999999").status_code == 404
