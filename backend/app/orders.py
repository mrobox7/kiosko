"""Saved orders. A draft is the cart; confirming it checks everything again and freezes it.

Every line is checked and priced by `pricing`, the same code that answers /orders/price."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models, pricing, schemas

DRAFT = "draft"
CONFIRMED = "confirmed"


class OrderError(Exception):
    """The request cannot be done. `status` is the HTTP status; `detail` is what to send back."""

    def __init__(self, status: int, detail: object) -> None:
        self.status = status
        self.detail = detail


def _rejected(status: int, cart: schemas.PricedCart) -> OrderError:
    return OrderError(
        status,
        {
            "missing": [i.model_dump() for i in cart.missing],
            "problems": [i.model_dump() for i in cart.problems],
        },
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
        outlet_id=order.outlet_id,
        phone=order.phone,
        email=order.email,
        status=order.status,
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
        raise OrderError(404, f"No order {order_id}")
    return order


def _draft(db: Session, order_id: int) -> models.Order:
    order = get(db, order_id)
    if order.status != DRAFT:
        raise OrderError(409, f"Order {order_id} is already {order.status}")
    return order


def create(db: Session, request: schemas.OrderCreate) -> models.Order:
    if db.get(models.Outlet, request.outlet_id) is None:
        raise OrderError(404, f"No outlet {request.outlet_id}")
    order = models.Order(
        outlet_id=request.outlet_id,
        phone=request.phone,
        email=request.email,
        status=DRAFT,
        created_at=datetime.now(UTC),
    )
    db.add(order)
    db.commit()
    return order


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
        raise _rejected(422, cart)
    order.lines.append(_line_row(cart.lines[0], line.note))
    db.commit()
    return order


def remove_line(db: Session, order_id: int, line_id: int) -> models.Order:
    order = _draft(db, order_id)
    line = next((x for x in order.lines if x.id == line_id), None)
    if line is None:
        raise OrderError(404, f"Order {order_id} has no line {line_id}")
    order.lines.remove(line)
    db.commit()
    return order


def confirm(db: Session, order_id: int) -> models.Order:
    """Check every line against the menu as it is now, then freeze the order.

    If a price changed since a line was added, the lines are updated to the new prices and the
    confirmation is refused, so the customer is told the new price before agreeing to it."""
    order = _draft(db, order_id)
    if not order.lines:
        raise OrderError(409, "The order has no items")
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
        raise _rejected(409, cart)

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
        raise _rejected(
            409,
            schemas.PricedCart(
                ready=False,
                lines=[],
                subtotal=Decimal(0),
                gst=Decimal(0),
                total=Decimal(0),
                missing=[],
                problems=changed,
            ),
        )

    order.status = CONFIRMED
    order.confirmed_at = datetime.now(UTC)
    order.subtotal, order.gst, order.total = cart.subtotal, cart.gst, cart.total
    db.commit()
    return order
