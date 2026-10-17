"""get_my_order_history: what the customer ordered on past bookings."""

from pydantic import BaseModel, Field

from app.domain.results import ToolResult
from app.memory.service import MemoryService
from app.tools.base import Tool, ToolContext


class GetMyOrderHistoryArgs(BaseModel):
    """Arguments of get_my_order_history."""

    limit: int = Field(default=10, ge=1, le=20, description="How many items to return")


class GetMyOrderHistory(Tool[GetMyOrderHistoryArgs]):
    """Recent ordered items, newest booking first."""

    name = "get_my_order_history"
    description = (
        "Use when the customer asks what they ordered before, or for 'the usual'. "
        "Not needed for the current booking: use get_reservation_orders for that."
    )
    args_model = GetMyOrderHistoryArgs

    def run(self, ctx: ToolContext, args: GetMyOrderHistoryArgs) -> ToolResult:
        lines = MemoryService(ctx.backend).order_history(ctx.require_customer())
        data: dict[str, object] = {
            "orders": [
                {
                    "date": line.slot.date().isoformat(),
                    "item": line.item,
                    "quantity": line.quantity,
                    "status": line.status,
                }
                for line in lines[: args.limit]
            ]
        }
        if len(lines) > args.limit:
            data["note"] = f"Showing {args.limit} of {len(lines)} items."
        return ToolResult.success(data)

    def compact(self, result: ToolResult, args: GetMyOrderHistoryArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        return f"{len(result.data['orders'])} past items"
