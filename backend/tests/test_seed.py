import copy
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.database import Base
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
        stored = db.get(models.Product, row["id"])
        assert stored is not None and stored.base_price == Decimal(row["base_price"])
    assert db.scalar(select(models.Product.base_price).where(models.Product.id == 1)) == Decimal(
        "60"
    )
    assert Decimal("205.71") in set(db.scalars(select(models.Product.base_price)))
    assert all(isinstance(p, Decimal) for p in db.scalars(select(models.Option.price_delta)))


def test_changed_price_in_the_file_reaches_the_database(db: Session) -> None:
    data = read_seed()
    load_seed(db, data)
    edited = copy.deepcopy(data)
    edited["products"][0]["base_price"] = Decimal("61.50")
    edited["meal_offers"][0]["price_delta"] = Decimal("140.00")
    load_seed(db, edited)
    db.expire_all()
    assert db.get(models.Product, edited["products"][0]["id"]).base_price == Decimal("61.50")  # type: ignore[union-attr]
    offer = edited["meal_offers"][0]
    stored = db.scalar(
        select(models.MealOffer).where(
            models.MealOffer.product_id == offer["product_id"],
            models.MealOffer.size == offer["size"],
        )
    )
    assert stored is not None and stored.price_delta == Decimal("140.00")
    load_seed(db, data)  # put the file's own values back


def test_groups_make_sense(db: Session) -> None:
    load_seed(db, read_seed())
    for group in db.scalars(select(models.OptionGroup)):
        assert group.options, group.name
        assert 0 <= group.min_select <= group.max_select, group.name
        assert group.min_select <= len(group.options), group.name
    for link in db.scalars(select(models.ProductOptionGroup)):
        low = link.min_select if link.min_select is not None else link.group.min_select
        high = link.max_select if link.max_select is not None else link.group.max_select
        assert 0 <= low <= high, (link.product_id, link.group_id)
