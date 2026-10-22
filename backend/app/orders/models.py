"""Order tables: an order, the items on it, and the options chosen on each item."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.menu.models import Outlet


class Order(Base):
    """A drive-thru order. A draft is the cart; confirming it freezes the lines and the totals."""

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("outlet_id", "business_date", "order_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(10))  # draft | confirmed | cancelled
    # The short number called out at the window; set on confirm, restarts every day per outlet.
    order_number: Mapped[int | None]
    business_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when confirmed, so a later change of the tax rate never rewrites a past order.
    subtotal: Mapped[Decimal | None]
    gst: Mapped[Decimal | None]
    total: Mapped[Decimal | None]

    outlet: Mapped[Outlet] = relationship()
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
    unit_price: Mapped[Decimal]  # one item, meal and options included

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
    price_delta: Mapped[Decimal]
