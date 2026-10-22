from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.menu.models import Product, ProductOptionGroup

Json = dict[str, Any]


def products(client: TestClient, **params: str) -> list[Json]:
    response = client.get("/products", params=params)
    assert response.status_code == 200
    body: list[Json] = response.json()
    return body


def by_name(client: TestClient, name: str) -> Json:
    found = [p for p in products(client) if p["name"] == name]
    assert len(found) == 1, name
    detail: Json = client.get(f"/products/{found[0]['id']}").json()
    return detail


def group(detail: Json, name: str) -> Json:
    found = [g for g in detail["option_groups"] if g["name"] == name]
    assert len(found) == 1, name
    result: Json = found[0]
    return result


def test_products_list_everything_active(client: TestClient) -> None:
    listed = products(client)
    assert len(listed) == 110
    assert len({p["id"] for p in listed}) == 110
    assert listed[0]["category"] == "burgers"


def test_prices_are_json_numbers(client: TestClient) -> None:
    tikki = next(p for p in products(client) if p["name"].startswith("McAloo Tikki"))
    assert tikki["base_price"] == 60
    assert not isinstance(tikki["base_price"], str)


def test_filter_by_category(client: TestClient) -> None:
    burgers = products(client, category="burgers")
    assert burgers and all(p["category"] == "burgers" for p in burgers)
    assert products(client, category="nope") == []


def test_filter_by_veg(client: TestClient) -> None:
    veg = products(client, veg="true")
    non_veg = products(client, veg="false")
    assert all(p["veg"] == "veg" for p in veg)
    assert all(p["veg"] == "non_veg" for p in non_veg)
    assert len(veg) + len(non_veg) == 110


def test_text_search_ignores_case_and_matches_description(client: TestClient) -> None:
    hits = products(client, q="MCSPICY")
    assert hits and all("mcspicy" in p["name"].lower() for p in hits)
    by_description = products(client, q="potato and peas")
    assert any("Tikki" in p["name"] for p in by_description)
    assert products(client, q="zzz-no-such-dish") == []
    percent = products(client, q="%")  # a wildcard character is just a character
    assert 0 < len(percent) < 110
    assert all("%" in f"{p['name']} {p['description']}" for p in percent)


def test_filters_combine(client: TestClient) -> None:
    both = products(client, category="burgers", veg="true", q="paneer")
    assert both and all(p["category"] == "burgers" and p["veg"] == "veg" for p in both)


def test_detail_has_the_choices_for_a_burger(client: TestClient) -> None:
    mcspicy = by_name(client, "McSpicy® Chicken")
    assert mcspicy["base_price"] == 205.71
    sauce = group(mcspicy, "Sauce")
    assert (sauce["min_select"], sauce["max_select"]) == (1, 1)
    cheese = group(mcspicy, "Cheese")
    assert cheese["min_select"] == 0
    assert {o["name"]: o["price_delta"] for o in cheese["options"]}["Double Cheese"] == 58.1
    assert mcspicy["image_url"] == "/images/180910797.png"
    assert mcspicy["nutrition"]["calories_kcal"] > 0


def test_product_limits_replace_the_group_limits(client: TestClient, db: Session) -> None:
    link = db.query(ProductOptionGroup).filter(ProductOptionGroup.max_select.is_not(None)).first()
    assert link is not None
    detail = client.get(f"/products/{link.product_id}").json()
    shown = next(g for g in detail["option_groups"] if g["id"] == link.group_id)
    assert shown["max_select"] == link.max_select
    if link.min_select is not None:
        assert shown["min_select"] == link.min_select


def test_meal_offers_medium_has_a_side_large_does_not(client: TestClient) -> None:
    offers = by_name(client, "McSpicy® Chicken")["meal_offers"]
    assert [o["size"] for o in offers] == ["Medium", "Large"]
    medium, large = offers
    assert medium["side"]["name"] == "Meal side (Medium)" and medium["side"]["min_select"] == 1
    assert large["side"] is None
    assert medium["drink"]["options"] and large["drink"]["options"]
    assert 0 < medium["price_delta"] < large["price_delta"] * 2


def test_a_combo_choice_points_at_real_products(client: TestClient) -> None:
    combo = by_name(client, "McVeggie/McChicken(Any Two)+1 Medium Fries+2 McPuff")
    assert combo["kind"] == "combo"
    linked = [o["linked_product_id"] for o in group(combo, "Burger choice")["options"]]
    assert len(linked) == 2
    for product_id in linked:
        assert client.get(f"/products/{product_id}").status_code == 200


def test_unknown_product_is_404(client: TestClient) -> None:
    assert client.get("/products/999999").status_code == 404


def test_inactive_product_is_hidden(client: TestClient, db: Session) -> None:
    product = db.get(Product, 1)
    assert product is not None
    product.is_active = False
    db.commit()
    try:
        assert client.get("/products/1").status_code == 404
        assert all(p["id"] != 1 for p in products(client))
        assert all(p["id"] != 1 for p in client.get("/catalog").json()["products"])
    finally:
        product.is_active = True
        db.commit()


def test_catalog_matches_the_other_endpoints(client: TestClient) -> None:
    catalog = client.get("/catalog").json()
    assert len(catalog["categories"]) == 8
    assert [p["id"] for p in catalog["products"]] == [p["id"] for p in products(client)]
    for entry in (catalog["products"][0], catalog["products"][40], catalog["products"][-1]):
        assert client.get(f"/products/{entry['id']}").json() == entry


def test_the_version_endpoint_agrees_with_the_catalog(client: TestClient) -> None:
    from tests.helpers import OUTLET

    for params in ({}, {"outlet": OUTLET}):
        version = client.get("/catalog/version", params=params).json()
        assert version == {"version": client.get("/catalog", params=params).json()["version"]}
    assert client.get("/catalog/version", params={"outlet": "nope"}).status_code == 404


def test_catalog_version_changes_with_the_menu(client: TestClient, db: Session) -> None:
    first = client.get("/catalog").json()["version"]
    assert client.get("/catalog").json()["version"] == first
    product = db.get(Product, 1)
    assert product is not None
    original = product.base_price
    product.base_price = original + Decimal("1.00")
    db.commit()
    try:
        assert client.get("/catalog").json()["version"] != first
    finally:
        product.base_price = original
        db.commit()
    assert client.get("/catalog").json()["version"] == first


def test_every_image_url_serves_a_picture(client: TestClient) -> None:
    listed = products(client)
    with_image = [p for p in listed if p["image_url"]]
    assert len(with_image) == 106 and len(listed) - len(with_image) == 4
    for p in with_image:
        response = client.get(p["image_url"])
        kind = "image/jpeg" if p["image_url"].endswith(".jpg") else "image/png"
        assert response.status_code == 200 and response.headers["content-type"] == kind
    assert client.get("/images/nope.png").status_code == 404


def test_the_seeded_outlet_has_a_code(db: Session) -> None:
    from app.menu.models import Outlet

    assert [o.code for o in db.query(Outlet).all()] == ["JPR-013-7429"]


def test_the_menu_leaves_out_what_the_outlet_is_not_selling(
    client: TestClient, db: Session
) -> None:
    from app.menu.models import Product, UnavailableProduct
    from tests.helpers import OUTLET

    hidden = db.query(Product).filter(Product.name == "McSpicy® Paneer").one()
    row = UnavailableProduct(outlet_id=1, product_id=hidden.id)
    db.add(row)
    db.commit()
    try:
        everyone = client.get("/catalog").json()["products"]
        assert hidden.id in {p["id"] for p in everyone}  # no outlet: nothing applied

        ours = client.get("/catalog", params={"outlet": OUTLET}).json()
        assert hidden.id not in {p["id"] for p in ours["products"]}

        listed = client.get("/products", params={"outlet": OUTLET}).json()
        assert hidden.id not in {p["id"] for p in listed}
        assert client.get(f"/products/{hidden.id}", params={"outlet": OUTLET}).status_code == 404
        assert client.get(f"/products/{hidden.id}").status_code == 200

        assert ours["version"] != client.get("/catalog").json()["version"]
    finally:
        db.delete(row)
        db.commit()
    assert client.get(f"/products/{hidden.id}", params={"outlet": OUTLET}).status_code == 200


def test_an_unknown_outlet_is_not_found(client: TestClient) -> None:
    for path in ("/catalog", "/products", "/products/1"):
        assert client.get(path, params={"outlet": "no-such-outlet"}).status_code == 404


def test_an_outlet_is_known_by_its_code_with_name_and_address(client: TestClient) -> None:
    from tests.helpers import OUTLET

    found = client.get(f"/outlets/{OUTLET}")
    assert found.status_code == 200
    body = found.json()
    assert body["code"] == OUTLET and body["name"] and body["address"]
    assert set(body) == {"code", "name", "address"}
    assert client.get("/outlets/nope").status_code == 404
