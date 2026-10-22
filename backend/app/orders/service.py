"""Saved orders. A draft is the cart; confirming it checks everything again and freezes it.

Every line is checked and priced by `pricing`, the same code that answers /orders/price."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.customers.models import Customer
from app.menu.models import Outlet
from app.menu.service import find_outlet
from app.orders import models, pricing, schemas

DRAFT = "draft"
CONFIRMED = "confirmed"
CANCELLED = "cancelled"
INDIA = timezone(timedelta(hours=5, minutes=30))  # the business day and order numbers follow it


class OrderError(Exception):
    """The request cannot be done. `status` is the HTTP status. `detail` is what is sent back:
    a machine-readable `code` and a `message`, plus `missing` and `problems` for a cart."""

    def __init__(self, status: int, code: str, message: str, **extra: object) -> None:
        self.status = status
        self.detail = {"code": code, "message": message, **extra}


def _rejected(
    status: int, missing: list[schemas.Issue], problems: list[schemas.Issue]
) -> OrderError:
    code, message = (
        ("invalid_line", "The item is incomplete or not valid")
        if status == 422
        else ("cannot_confirm", "The order cannot be placed as it is")
    )
    return OrderError(
        status,
        code,
        message,
        missing=[i.model_dump() for i in missing],
        problems=[i.model_dump() for i in problems],
    )


def _line_out(line: models.OrderLine) -> schemas.OrderLineOut:
    return schemas.OrderLineOut(
        id=line.id,
        product_id=line.product_id,
        name=line.name,
        quantity=line.quantity,
        meal_size=line.meal_size,
        note=line.note,
        unit_price=line.unit_price,
        line_total=line.unit_price * line.quantity,
        options=[
            schemas.PricedOption(
                option_id=o.option_id,
                group=o.group,
                name=o.name,
                qty=o.qty,
                price_delta=o.price_delta,
                total=o.price_delta * o.qty,
            )
            for o in line.options
        ],
    )


def view(order: models.Order) -> schemas.OrderOut:
    lines = [_line_out(line) for line in order.lines]
    if order.status == CONFIRMED:
        assert order.subtotal is not None and order.gst is not None and order.total is not None
        subtotal, tax, total = order.subtotal, order.gst, order.total
    else:
        subtotal = sum((line.line_total for line in lines), Decimal(0))
        tax = pricing.gst(subtotal)
        total = subtotal + tax
    return schemas.OrderOut(
        id=order.id,
        outlet=order.outlet.code,
        customer_id=order.customer_id,
        status=order.status,
        order_number=order.order_number,
        created_at=order.created_at,
        confirmed_at=order.confirmed_at,
        lines=lines,
        subtotal=subtotal,
        gst=tax,
        total=total,
    )


def get(db: Session, order_id: int) -> models.Order:
    order = db.get(models.Order, order_id)
    if order is None:
        raise OrderError(404, "not_found", f"No order {order_id}")
    return order


def _draft(db: Session, order_id: int) -> models.Order:
    order = get(db, order_id)
    if order.status != DRAFT:
        raise OrderError(409, "order_closed", f"Order {order_id} is already {order.status}")
    return order


def create(db: Session, request: schemas.OrderCreate) -> models.Order:
    outlet = find_outlet(db, request.outlet)
    if outlet is None:
        raise OrderError(404, "not_found", f"No outlet {request.outlet}")
    if request.customer_id is not None and db.get(Customer, request.customer_id) is None:
        raise OrderError(404, "not_found", f"No customer {request.customer_id}")
    order = models.Order(
        outlet_id=outlet.id,
        customer_id=request.customer_id,
        status=DRAFT,
        created_at=datetime.now(UTC),
    )
    db.add(order)
    db.commit()
    return order


def attach_customer(db: Session, order_id: int, customer_id: int) -> models.Order:
    """Put a draft on a customer, for when the customer is identified after ordering began."""
    order = _draft(db, order_id)
    if db.get(Customer, customer_id) is None:
        raise OrderError(404, "not_found", f"No customer {customer_id}")
    order.customer_id = customer_id
    db.commit()
    return order


def _next_order_number(db: Session, outlet_id: int, day: date) -> int:
    """The next number for this outlet today. The outlet row is locked while it is picked, so two
    orders confirmed at the same moment cannot get the same number."""
    db.execute(select(Outlet).where(Outlet.id == outlet_id).with_for_update())
    last = db.scalar(
        select(func.max(models.Order.order_number)).where(
            models.Order.outlet_id == outlet_id, models.Order.business_date == day
        )
    )
    return (last or 0) + 1


def _line_row(priced: schemas.PricedLine, note: str | None = None) -> models.OrderLine:
    return models.OrderLine(
        product_id=priced.product_id,
        quantity=priced.quantity,
        meal_size=priced.meal_size,
        note=note,
        name=priced.name,
        unit_price=priced.unit_price,
        options=[
            models.OrderLineOption(
                option_id=o.option_id,
                group=o.group,
                name=o.name,
                qty=o.qty,
                price_delta=o.price_delta,
            )
            for o in priced.options
        ],
    )


def add_line(db: Session, order_id: int, line: schemas.CartLine) -> models.Order:
    """Add a complete, valid line. Anything missing or wrong is refused and nothing is saved."""
    order = _draft(db, order_id)
    cart = pricing.price_cart(db, order.outlet_id, [line])
    if not cart.ready:
        raise _rejected(422, cart.missing, cart.problems)
    order.lines.append(_line_row(cart.lines[0], line.note))
    db.commit()
    return order


def _line(order: models.Order, line_id: int) -> models.OrderLine:
    line = next((x for x in order.lines if x.id == line_id), None)
    if line is None:
        raise OrderError(404, "not_found", f"Order {order.id} has no line {line_id}")
    return line


def remove_line(db: Session, order_id: int, line_id: int) -> models.Order:
    order = _draft(db, order_id)
    order.lines.remove(_line(order, line_id))
    db.commit()
    return order


def set_quantity(db: Session, order_id: int, line_id: int, quantity: int) -> models.Order:
    """Change how many of a line's item are wanted. The line keeps its id and its price."""
    order = _draft(db, order_id)
    _line(order, line_id).quantity = quantity
    db.commit()
    return order


def cancel(db: Session, order_id: int) -> models.Order:
    """Abandon a draft: the customer started over, left, or timed out. The order and its lines
    are kept, but it can no longer be changed or confirmed. Cancelling twice is harmless, so a
    caller that is unsure whether the first attempt went through can simply repeat it."""
    order = get(db, order_id)
    if order.status == CANCELLED:
        return order
    order = _draft(db, order_id)  # a confirmed order cannot be cancelled
    order.status = CANCELLED
    db.commit()
    return order


def confirm(db: Session, order_id: int) -> models.Order:
    """Check every line against the menu as it is now, then freeze the order.

    If a price changed since a line was added, the lines are updated to the new prices and the
    confirmation is refused, so the customer is told the new price before agreeing to it."""
    order = _draft(db, order_id)
    if not order.lines:
        raise OrderError(409, "empty_order", "The order has no items")
    cart = pricing.price_cart(
        db,
        order.outlet_id,
        [
            schemas.CartLine(
                product_id=line.product_id,
                quantity=line.quantity,
                meal_size=line.meal_size,
                options=[
                    schemas.OptionPick(option_id=o.option_id, qty=o.qty) for o in line.options
                ],
            )
            for line in order.lines
        ],
    )
    if not cart.ready:
        raise _rejected(409, cart.missing, cart.problems)

    changed: list[schemas.Issue] = []
    for index, (line, priced) in enumerate(zip(order.lines, cart.lines, strict=True)):
        if line.unit_price != priced.unit_price:
            changed.append(
                schemas.Issue(
                    line=index,
                    code="price_changed",
                    message=f"{line.name} now costs {priced.unit_price} (was {line.unit_price})",
                )
            )
            fresh = _line_row(priced, line.note)
            line.name, line.unit_price, line.options = fresh.name, fresh.unit_price, fresh.options
    if changed:
        db.commit()
        raise _rejected(409, [], changed)

    order.status = CONFIRMED
    order.confirmed_at = datetime.now(UTC)
    order.business_date = order.confirmed_at.astimezone(INDIA).date()
    order.order_number = _next_order_number(db, order.outlet_id, order.business_date)
    order.subtotal, order.gst, order.total = cart.subtotal, cart.gst, cart.total
    db.commit()
    return order
