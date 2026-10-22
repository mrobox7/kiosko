"""Menu tables: what is sold, how it can be customised, and which outlet sells it."""

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
    base_price: Mapped[Decimal]
    image_key: Mapped[str | None] = mapped_column(String(100))  # file under static/
    nutrition: Mapped[dict[str, Any]] = mapped_column(JSON)
    allergens: Mapped[list[str]] = mapped_column(JSON)  # milk, gluten, egg, soy, fish
    tags: Mapped[list[str]] = mapped_column(JSON)
    is_active: Mapped[bool]
    sort_order: Mapped[int]

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
    price_delta: Mapped[Decimal]
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
    price_delta: Mapped[Decimal]
    side_group_id: Mapped[int | None] = mapped_column(ForeignKey("option_groups.id"))
    drink_group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id"))

    side_group: Mapped[OptionGroup | None] = relationship(foreign_keys=[side_group_id])
    drink_group: Mapped[OptionGroup] = relationship(foreign_keys=[drink_group_id])


class Outlet(Base):
    __tablename__ = "outlets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # what the drive-thru is set up with
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str]


class UnavailableProduct(Base):
    """A product one outlet is not selling right now. Delete the row to sell it again."""

    __tablename__ = "unavailable_products"

    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)


class UnavailableOption(Base):
    """An option one outlet is not offering, such as a drink it has run out of. Delete the row to
    offer it again."""

    __tablename__ = "unavailable_options"

    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), primary_key=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), primary_key=True)
