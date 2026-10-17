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
        entry = ctx.ledger(self.name, "removed", order.id)
        data = {
            "removed_order_id": order.id,
            "reservation_id": order.reservation_id,
            "menu_item_id": order.menu_item_id,
            "quantity": order.quantity,
        }
        return ToolResult(ok=True, data=data, writes=[entry])

    def compact(self, result: ToolResult, args: RemoveOrderItemArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        d = result.data
        return (
            f"order {d['removed_order_id']}: removed item #{d['menu_item_id']} x{d['quantity']}"
            f" from booking #{d['reservation_id']}"
        )
