import copy
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.menu.models import MealOffer, Option, OptionGroup, Outlet, Product, ProductOptionGroup
from app.seed import SEED_PATH, TABLES, load_seed, read_seed

IMAGES = SEED_PATH.parent.parent / "static" / "images"


def count(db: Session, model: type[Base]) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_seed_file_is_clean() -> None:
    data = read_seed()
    text = SEED_PATH.read_text().lower()
    assert "swiggy" not in text
    assert all(p["sku"].startswith("mcd-") for p in data["products"])
    assert len({p["sku"] for p in data["products"]}) == len(data["products"])


def test_every_image_in_the_seed_exists() -> None:
    keys = {p["image_key"] for p in read_seed()["products"] if p["image_key"]}
    assert keys
    assert all((IMAGES / Path(k).name).is_file() for k in keys)
    assert {f.name for f in IMAGES.iterdir()} == {Path(k).name for k in keys}  # no spare files


def test_load_inserts_every_row(db: Session) -> None:
    data = read_seed()
    counts = load_seed(db, data)
    for key, model, _ in TABLES:
        assert counts[key] == len(data[key])
        assert count(db, model) == len(data[key])


def test_load_twice_changes_nothing(db: Session) -> None:
    data = read_seed()
    load_seed(db, data)
    load_seed(db, data)
    for key, model, _ in TABLES:
        assert count(db, model) == len(data[key])


def test_prices_are_exact(db: Session) -> None:
    data = read_seed()
    load_seed(db, data)
    for row in data["products"]:
        stored = db.get(Product, row["id"])
        assert stored is not None and stored.base_price == Decimal(row["base_price"])
    assert db.scalar(select(Product.base_price).where(Product.id == 1)) == Decimal("60")
    assert Decimal("205.71") in set(db.scalars(select(Product.base_price)))
    assert all(isinstance(p, Decimal) for p in db.scalars(select(Option.price_delta)))


def test_changed_price_in_the_file_reaches_the_database(db: Session) -> None:
    data = read_seed()
    load_seed(db, data)
    edited = copy.deepcopy(data)
    edited["products"][0]["base_price"] = Decimal("61.50")
    edited["meal_offers"][0]["price_delta"] = Decimal("140.00")
    load_seed(db, edited)
    db.expire_all()
    assert db.get(Product, edited["products"][0]["id"]).base_price == Decimal("61.50")  # type: ignore[union-attr]
    offer = edited["meal_offers"][0]
    stored = db.scalar(
        select(MealOffer).where(
            MealOffer.product_id == offer["product_id"],
            MealOffer.size == offer["size"],
        )
    )
    assert stored is not None and stored.price_delta == Decimal("140.00")
    load_seed(db, data)  # put the file's own values back


def test_groups_make_sense(db: Session) -> None:
    load_seed(db, read_seed())
    for group in db.scalars(select(OptionGroup)):
        assert group.options, group.name
        assert 0 <= group.min_select <= group.max_select, group.name
        assert group.min_select <= len(group.options), group.name
    for link in db.scalars(select(ProductOptionGroup)):
        low = link.min_select if link.min_select is not None else link.group.min_select
        high = link.max_select if link.max_select is not None else link.group.max_select
        assert 0 <= low <= high, (link.product_id, link.group_id)


NUTRITION_KEYS = {"calories_kcal", "protein_g", "fat_g", "carbs_g", "sugar_g", "sodium_mg"}
ALLERGENS = {"milk", "gluten", "egg", "soy", "fish"}


def test_every_product_has_nutrition_and_a_clean_allergen_list() -> None:
    for product in read_seed()["products"]:
        nutrition = product["nutrition"]
        assert NUTRITION_KEYS <= nutrition.keys(), product["name"]
        assert all(nutrition[k] is not None and nutrition[k] >= 0 for k in NUTRITION_KEYS)
        assert isinstance(product["allergens"], list), product["name"]
        assert set(product["allergens"]) <= ALLERGENS, product["name"]
        assert product["allergens"] == sorted(set(product["allergens"]))


def test_nutrition_adds_up_roughly() -> None:
    """Calories should be close to 4 x protein + 9 x fat + 4 x carbs."""
    for product in read_seed()["products"]:
        n = product["nutrition"]
        if n["calories_kcal"] < 50:
            continue
        counted = 4 * n["protein_g"] + 9 * n["fat_g"] + 4 * n["carbs_g"]
        assert abs(counted - n["calories_kcal"]) <= 0.15 * n["calories_kcal"] + 5, product["name"]
        assert n["sugar_g"] <= n["carbs_g"] + 0.5, product["name"]


def test_obvious_allergens_are_listed() -> None:
    by_name = {p["name"]: p["allergens"] for p in read_seed()["products"]}
    assert "milk" in by_name["Chocolate Shake"] and "milk" in by_name["Latte"]
    assert "milk" in by_name["McSpicy® Paneer"]
    assert by_name["Coke"] == [] and by_name["Schweppes™ Bottled Water"] == []
    assert by_name["Fries"] == []  # nothing in it but potato and salt


def test_rows_added_after_loading_get_fresh_ids(db: Session) -> None:
    load_seed(db, read_seed())
    outlet = Outlet(code="another-outlet", name="Another outlet", address="Elsewhere")
    db.add(outlet)
    db.commit()
    try:
        assert outlet.id > max(o["id"] for o in read_seed()["outlets"])
    finally:
        db.delete(outlet)
        db.commit()
