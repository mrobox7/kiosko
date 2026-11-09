"""cancel_order: throw the order away and start again."""

from pydantic import BaseModel

from app.tools.backend_errors import settle
from app.tools.contract import Tool, ToolContext, ToolResult, Update


class CancelOrderArgs(BaseModel):
    """Arguments of cancel_order: none, it cancels this chat's order."""


class CancelOrder(Tool[CancelOrderArgs]):
    """Start the order over."""

    name = "cancel_order"
    args_model = CancelOrderArgs

    def run(self, ctx: ToolContext, args: CancelOrderArgs) -> ToolResult:
        order = ctx.order
        if order is None:
            return ToolResult.failure("no_order", "There is no order yet.", "Nothing to cancel.")
        if ctx.placed:
            return ToolResult.failure(
                "already_placed",
                f"Order {order.id} is already placed as number {order.order_number}.",
                "A placed order cannot be cancelled here.",
            )
        # Cancelling twice is the same as once, so a lost reply is just resent.
        settle(lambda: ctx.backend.cancel_order(order.id), landed=lambda: None)
        data = {
            "cancelled_order_id": order.id,
            "lines_removed": len(order.lines),
            "note": "The order is cancelled. The next dish starts a new order.",
        }
        # The next dish starts a new order.
        return ToolResult(ok=True, data=data, changed=True, update=Update(clear_order=True))
