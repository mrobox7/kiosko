"""Load seed/seed.json into the database. Safe to run again: rows are matched by id and updated.

    uv run python -m app.seed

Rows that are no longer in the file are left alone."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Table, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, create_tables, engine
from app.menu import models

SEED_PATH = Path(__file__).resolve().parent.parent / "seed" / "seed.json"

# (seed key, model, columns that identify a row), in an order that keeps every link valid.
TABLES: list[tuple[str, type[Base], tuple[str, ...]]] = [
    ("categories", models.Category, ("id",)),
    ("products", models.Product, ("id",)),
    ("option_groups", models.OptionGroup, ("id",)),
    ("options", models.Option, ("id",)),
    ("product_option_groups", models.ProductOptionGroup, ("product_id", "group_id")),
    ("meal_offers", models.MealOffer, ("product_id", "size")),
    ("outlets", models.Outlet, ("id",)),
]


# The price field of each seed table.
PRICE_FIELDS = {"products": "base_price", "options": "price_delta", "meal_offers": "price_delta"}


def read_seed(path: Path = SEED_PATH) -> dict[str, Any]:
    """Prices are turned into exact decimals, never kept as floats."""
    data: dict[str, Any] = json.loads(path.read_text())
    for key, field in PRICE_FIELDS.items():
        for row in data[key]:
            row[field] = Decimal(str(row[field]))
    return data


def load_seed(db: Session, data: dict[str, Any]) -> dict[str, int]:
    """Insert or update every row in `data`. Returns the number of rows per table."""
    counts: dict[str, int] = {}
    for key, model, identity in TABLES:
        columns = {c.name for c in model.__table__.columns}
        rows = [{k: v for k, v in row.items() if k in columns} for row in data[key]]
        counts[key] = len(rows)
        if not rows:
            continue
        statement = pg_insert(model).values(rows)
        changes = {c: statement.excluded[c] for c in rows[0] if c not in identity}
        db.execute(statement.on_conflict_do_update(index_elements=list(identity), set_=changes))
        if identity == ("id",):
            _continue_ids_after_the_highest(db, model)
    db.commit()
    return counts


def _continue_ids_after_the_highest(db: Session, model: type[Base]) -> None:
    """Rows were inserted with their own ids, so the database's id counter did not move. Without
    this, the next row added without an id would try to take id 1 again."""
    table = cast(Table, model.__table__)
    sequence = db.scalar(func.pg_get_serial_sequence(table.name, "id"))
    top = db.scalar(select(func.max(table.c.id)))
    if sequence and top:
        db.execute(select(func.setval(sequence, top)))


def main() -> None:
    create_tables(engine)
    with SessionLocal() as db:
        for table, count in load_seed(db, read_seed()).items():
            print(f"{table}: {count}")


if __name__ == "__main__":
    main()
