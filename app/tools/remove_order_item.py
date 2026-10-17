"""remove_order_item: take a dish off a booking."""

from pydantic import BaseModel

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.checks import own_order


class RemoveOrderItemArgs(BaseModel):
    """Arguments of remove_order_item."""

    order_id: int


class RemoveOrderItem(Tool[RemoveOrderItemArgs]):
    """Remove one order line."""

    name = "remove_order_item"
    description = "Use to remove an ordered item. The order_id comes from get_reservation_orders."
    args_model = RemoveOrderItemArgs
    mutating = True

    def run(self, ctx: ToolContext, args: RemoveOrderItemArgs) -> ToolResult:
        order = own_order(ctx, args.order_id)
        ctx.backend.delete_order(order.id)
        entry = ctx.ledger(
            self.name,
            "removed",
            order.id,
            f"Removed item #{order.menu_item_id} x{order.quantity}"
            f" from reservation #{order.reservation_id}",
        )
        return ToolResult(ok=True, data={"removed_order_id": order.id}, writes=[entry])
