"""Ownership checks. The backend does not check who owns what, so every tool that takes a
reservation or order id goes through here."""

from app.backend.errors import BackendNotFound
from app.backend.models import Order, Reservation
from app.tools.base import NotPermitted, ToolContext


def own_reservation(ctx: ToolContext, reservation_id: int) -> Reservation:
    """The reservation, if it is the bound customer's. Missing and foreign ids look the same."""
    customer_id = ctx.require_customer()
    try:
        reservation = ctx.backend.get_reservation(reservation_id)
    except BackendNotFound as exc:
        raise NotPermitted(f"reservation {reservation_id}") from exc
    if reservation.customer_id != customer_id:
        raise NotPermitted(f"reservation {reservation_id}")
    return reservation


def own_order(ctx: ToolContext, order_id: int) -> Order:
    """The order, found among the bound customer's own orders."""
    customer_id = ctx.require_customer()
    for order in ctx.backend.list_customer_orders(customer_id):
        if order.id == order_id:
            return order
    raise NotPermitted(f"order {order_id}")
