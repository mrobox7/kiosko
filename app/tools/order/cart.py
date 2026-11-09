"""The order as the model reads it, and how a line of it is found. One shape in every order tool:
`line_id` names a line, `line_total` is the whole line (quantity and choices included), and the
order has `subtotal`, `gst` and `total`, all in rupees with GST added to the total."""

from typing import Any

from app.backend.models import Line, Order
from app.menu.lookup import LookupFailed, find_line
from app.menu.names import dish_name, option_name
from app.tools.contract import ToolContext


def line_view(line: Line) -> dict[str, Any]:
    view: dict[str, Any] = {
        "line_id": line.id,
        "name": dish_name(line.name),
        "quantity": line.quantity,
        "line_total": line.line_total,
    }
    if line.meal_size:
        view["meal_size"] = line.meal_size
    if line.options:
        view["options"] = [
            option_name(o["name"]) if o["qty"] == 1 else f"{o['qty']}x {option_name(o['name'])}"
            for o in line.options
        ]
    if line.note:
        view["note"] = line.note
    return view


def cart_view(order: Order) -> dict[str, Any]:
    """Every line and the totals."""
    return {
        "order_id": order.id,
        "lines": [line_view(line) for line in order.lines],
        "subtotal": order.subtotal,
        "gst": order.gst,
        "total": order.total,
    }


def pick_line(ctx: ToolContext, name: str | None, line_id: int | None) -> Line:
    """The line of this chat's order that was named or numbered. Works on the copy the chat holds,
    so it needs no request."""
    latest = ctx.order
    if latest is None:
        raise LookupFailed("no_order", "There is no order yet.", "Nothing to change; add a dish.")
    if not latest.lines:
        raise LookupFailed("unknown_line", "The order is empty.", "Add a dish first.")
    if line_id is None:
        assert name is not None  # the arguments allow a name or a number, never neither
        return find_line(latest.lines, name)
    for line in latest.lines:
        if line.id == line_id:
            return line
    on_order = ", ".join(f"{line.id} {dish_name(line.name)}" for line in latest.lines)
    raise LookupFailed(
        "unknown_line", f"Line {line_id} is not on the order", f"Lines on the order: {on_order}"
    )
