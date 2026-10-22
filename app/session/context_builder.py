"""Builds the per-turn context message. Holds no state.

The system message is fixed text and is never mixed with anything that changes: the time, the
order so far, who is ordering and the summary all live in this separate message, which the Session
puts right before the customer's own message. The voice rules are here too, on spoken turns
only, so typed and spoken turns share the same system message."""

from datetime import datetime

from app.backend.models import DriveThruLine
from app.domain.state import ActiveOrder, Caller
from app.menu.names import dish_name, option_name
from app.session.prompts import VOICE_PROMPT

HEADING = "Context for this turn"


def _line(line: DriveThruLine) -> str:
    parts = [f"{line.quantity} x {dish_name(line.name)}"]
    if line.meal_size:
        parts.append(f"{line.meal_size} meal")
    parts += [
        option_name(o["name"]) if o["qty"] == 1 else f"{o['qty']}x {option_name(o['name'])}"
        for o in line.options
    ]
    if line.note:
        parts.append(f"note: {line.note}")
    return f"- line {line.id}: {', '.join(parts)} = {line.line_total}"


def _order_block(order: ActiveOrder) -> list[str]:
    """The cart as the server last reported it, so the model never has to remember it."""
    latest = order.latest
    if latest is None or not latest.lines:
        return ["Order so far: empty"]
    totals = f"Subtotal {latest.subtotal}, GST {latest.gst}, Total {latest.total}"
    heading = "Order so far (prices in rupees, GST is added to the total):"
    if order.placed:  # the summary leaves place_order out, so the order itself says it
        heading = f"Order PLACED as number {latest.order_number} (prices in rupees, GST included):"
    return [
        heading,
        *map(_line, latest.lines),
        totals,
    ]


def _customer_block(caller: Caller) -> list[str]:
    customer = caller.customer
    if customer is None:
        return ["Customer: not identified"]
    lines = [f"Customer: {customer.name or 'identified, no name given'}"]
    if caller.usual:
        lines.append(f"Usually orders: {', '.join(caller.usual)}")
    return lines


def _needs_block(caller: Caller) -> list[str]:
    """What must limit every suggestion: allergies (on file or said now) and a vegetarian diet."""
    said = [f"allergic to {', '.join(caller.avoid)}"] if caller.avoid else []
    said += ["vegetarian only"] if caller.needs.veg_only else []
    return [f"Needs: {'; '.join(said)}"] if said else []


def build_context(
    now: datetime, order: ActiveOrder, caller: Caller, earlier: str = "", spoken: bool = False
) -> str:
    """Everything the model needs that is not the customer's words and changes between turns. On a
    spoken turn the voice rules come last."""
    return "\n".join(
        [
            f"{HEADING}:",
            f"Current date and time: {now:%A %Y-%m-%d %H:%M} ({now.tzname()})",
            *_customer_block(caller),
            *_needs_block(caller),
            *_order_block(order),
            *([earlier] if earlier else []),
            *([VOICE_PROMPT] if spoken else []),
        ]
    )
