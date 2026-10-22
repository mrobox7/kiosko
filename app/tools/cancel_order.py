"""cancel_order: throw the order away and start again."""

from pydantic import BaseModel

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.recover import settle


class CancelOrderArgs(BaseModel):
    """Arguments of cancel_order: none, it cancels this chat's order."""


class CancelOrder(Tool[CancelOrderArgs]):
    """Start the order over."""

    name = "cancel_order"
    description = (
        'Cancel the whole order so the customer can start over: only when they say so ("forget '
        'it", "start again"), and ask first if there is more than one line on it. It cannot be '
        "undone. The next add_to_order starts a new order. It cannot cancel an order that has "
        "been placed."
    )
    args_model = CancelOrderArgs
    mutating = True
    shown_in_order = True
    destructive = True

    def run(self, ctx: ToolContext, args: CancelOrderArgs) -> ToolResult:
        order = ctx.order.latest
        if order is None:
            return ToolResult.failure("no_order", "There is no order yet.", "Nothing to cancel.")
        if ctx.order.placed:
            return ToolResult.failure(
                "already_placed",
                f"Order {order.id} is already placed as number {order.order_number}.",
                "A placed order cannot be cancelled here.",
            )
        # Cancelling twice is the same as once, so a lost reply is just resent.
        settle(lambda: ctx.backend.cancel_order(order.id), landed=lambda: None)
        ctx.order.latest = None  # the next dish starts a new order
        data = {
            "cancelled_order_id": order.id,
            "lines_removed": len(order.lines),
            "note": "The order is cancelled. The next dish starts a new order.",
        }
        return ToolResult(ok=True, data=data, changed=True)

    def compact(self, result: ToolResult, args: CancelOrderArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        d = result.data
        return f"order {d['cancelled_order_id']} cancelled ({d['lines_removed']} lines removed)"
