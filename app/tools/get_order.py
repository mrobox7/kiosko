"""get_order: what is on the customer's order now."""

from pydantic import BaseModel

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.cart import cart_view


class GetOrderArgs(BaseModel):
    """Arguments of get_order: none, it reads this chat's order."""


class GetOrder(Tool[GetOrderArgs]):
    """Read the order back."""

    name = "get_order"
    description = (
        "What is on the customer's order now, with its totals. Use it to read the order back "
        "before placing it or when the customer asks what they have."
    )
    args_model = GetOrderArgs

    def run(self, ctx: ToolContext, args: GetOrderArgs) -> ToolResult:
        order = ctx.order.latest
        if order is None or not order.lines:
            return ToolResult.success({"lines": [], "note": "The order is empty."})
        return ToolResult.success(cart_view(order))

    def compact(self, result: ToolResult, args: GetOrderArgs) -> str:
        d = result.data
        if not result.ok or not d["lines"]:
            return "order: empty"
        return f"order {d['order_id']}: {len(d['lines'])} lines, total {d['total']}"
