"""Customers: who is ordering, what they like, and what they ordered before."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.customers import models, schemas
from app.menu.models import Product
from app.orders.models import Order, OrderLine


def identify(db: Session, request: schemas.CustomerCreate) -> tuple[models.Customer, bool]:
    """Find the customer by phone, or add them. Returns the customer and whether it is new.
    For someone already known, a name or email they did not have before is filled in; nothing
    they already have is overwritten."""
    found = db.scalars(
        select(models.Customer).where(models.Customer.phone == request.phone)
    ).first()
    if found is None:
        found = models.Customer(
            phone=request.phone,
            name=request.name,
            email=request.email,
            preferences={},
            created_at=datetime.now(UTC),
        )
        db.add(found)
        db.commit()
        return found, True
    found.name = found.name or request.name
    found.email = found.email or request.email
    db.commit()
    return found, False


def update_preferences(db: Session, customer: models.Customer, changes: dict[str, Any]) -> None:
    """Shallow merge: a key given here replaces that key; other keys stay."""
    customer.preferences = {**customer.preferences, **changes}
    db.commit()


def confirmed_orders(db: Session, customer_id: int, limit: int) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.customer_id == customer_id, Order.status == "confirmed")
        .order_by(Order.confirmed_at.desc(), Order.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def open_draft(db: Session, customer_id: int) -> Order | None:
    """The latest cart that has something in it, so a customer can carry on where they stopped."""
    stmt = (
        select(Order)
        .where(
            Order.customer_id == customer_id,
            Order.status == "draft",
            Order.lines.any(),
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    return db.scalars(stmt).first()


def favourites(db: Session, customer_id: int, limit: int) -> list[schemas.Favourite]:
    """Products still on the menu, most ordered first."""
    stmt = (
        select(
            Product.id,
            Product.name,
            func.count(Order.id.distinct()),
            func.sum(OrderLine.quantity),
            func.max(Order.confirmed_at),
        )
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .join(Product, Product.id == OrderLine.product_id)
        .where(
            Order.customer_id == customer_id,
            Order.status == "confirmed",
            Product.is_active,
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderLine.quantity).desc(), func.max(Order.confirmed_at).desc())
        .limit(limit)
    )
    found: list[schemas.Favourite] = []
    for pid, name, orders, quantity, last in db.execute(stmt):
        assert last is not None  # a confirmed order always has its confirmation time
        found.append(
            schemas.Favourite(
                product_id=pid,
                name=name,
                times_ordered=orders,
                total_quantity=int(quantity),
                last_ordered_at=last,
            )
        )
    return found
