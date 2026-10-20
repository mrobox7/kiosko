"""Catalog tables: what is sold, how it can be customised, and which outlet sells it.

Money is exact decimal rupees, before tax. Orders are added in a later step."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

Money = Numeric(10, 2)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int]


class Product(Base):
    """One menu item, or a combo (a bundle whose parts are chosen through option groups)."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    kind: Mapped[str] = mapped_column(String(10))  # item | combo
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None]  # 34 products have none in the source
    veg: Mapped[str] = mapped_column(String(10))  # veg | non_veg
    base_price: Mapped[Decimal] = mapped_column(Money)
    image_key: Mapped[str | None] = mapped_column(String(100))  # file under static/
    nutrition: Mapped[dict[str, Any]] = mapped_column(JSON)
    allergens: Mapped[dict[str, Any]] = mapped_column(JSON)
    tags: Mapped[list[str]] = mapped_column(JSON)
    is_active: Mapped[bool]
    sort_order: Mapped[int]
    source_ref: Mapped[str | None] = mapped_column(String(50))  # id in the source data

    category: Mapped[Category] = relationship()
    option_links: Mapped[list[ProductOptionGroup]] = relationship(
        order_by="ProductOptionGroup.sort_order"
    )
    meal_offers: Mapped[list[MealOffer]] = relationship(order_by="MealOffer.price_delta")


class OptionGroup(Base):
    """A question with limits, such as Sauce (pick exactly 1) or Cheese (pick up to 2)."""

    __tablename__ = "option_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    min_select: Mapped[int]  # 1 or more: the customer must answer
    max_select: Mapped[int]

    options: Mapped[list[Option]] = relationship(order_by="Option.sort_order")


class Option(Base):
    """An answer inside a group. `linked_product_id` is set when the answer is itself a product."""

    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id"))
    name: Mapped[str] = mapped_column(String(200))
    price_delta: Mapped[Decimal] = mapped_column(Money)
    is_default: Mapped[bool]
    sort_order: Mapped[int]
    linked_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))


class ProductOptionGroup(Base):
    """Which product asks which group, with optional limits that replace the group's own."""

    __tablename__ = "product_option_groups"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id"), primary_key=True)
    min_select: Mapped[int | None]
    max_select: Mapped[int | None]
    sort_order: Mapped[int]

    group: Mapped[OptionGroup] = relationship()


class MealOffer(Base):
    """'Make it a meal' for one product: a size, its extra price and what the side and drink are.
    Large meals have no side choice, so `side_group_id` can be empty."""

    __tablename__ = "meal_offers"
    __table_args__ = (UniqueConstraint("product_id", "size"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    size: Mapped[str] = mapped_column(String(10))  # Medium | Large
    price_delta: Mapped[Decimal] = mapped_column(Money)
    side_group_id: Mapped[int | None] = mapped_column(ForeignKey("option_groups.id"))
    drink_group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id"))
    source_ref: Mapped[str | None] = mapped_column(String(50))

    side_group: Mapped[OptionGroup | None] = relationship(foreign_keys=[side_group_id])
    drink_group: Mapped[OptionGroup] = relationship(foreign_keys=[drink_group_id])


class Outlet(Base):
    __tablename__ = "outlets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str]
    source_ref: Mapped[str | None] = mapped_column(String(50))


class OutletProduct(Base):
    """An exception for one outlet. A product with no row here is available at its base price."""

    __tablename__ = "outlet_products"

    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    available: Mapped[bool] = mapped_column(default=True)
    price_override: Mapped[Decimal | None] = mapped_column(Money)


class Order(Base):
    """A drive-thru order. A draft is the cart; confirming it freezes the lines and the totals."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10))  # draft | confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when confirmed, so a later change of the tax rate never rewrites a past order.
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    gst: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)

    lines: Mapped[list[OrderLine]] = relationship(
        order_by="OrderLine.id", cascade="all, delete-orphan"
    )


class OrderLine(Base):
    """One product on an order. Names and prices are copies, so the menu can change later."""

    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    meal_size: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    unit_price: Mapped[Decimal] = mapped_column(Money)  # one item, meal and options included

    options: Mapped[list[OrderLineOption]] = relationship(
        order_by="OrderLineOption.id", cascade="all, delete-orphan"
    )


class OrderLineOption(Base):
    __tablename__ = "order_line_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("order_lines.id"))
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"))
    group: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    qty: Mapped[int]
    price_delta: Mapped[Decimal] = mapped_column(Money)
