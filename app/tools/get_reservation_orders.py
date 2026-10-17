"""get_reservation_orders: what is ordered against a booking."""

from pydantic import BaseModel

from app.backend.models import MenuFilters
from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.checks import own_reservation


class GetReservationOrdersArgs(BaseModel):
    """Arguments of get_reservation_orders."""

    reservation_id: int


class GetReservationOrders(Tool[GetReservationOrdersArgs]):
    """List items ordered against one reservation."""

    name = "get_reservation_orders"
    description = (
        "Use to see what is currently ordered for a reservation. Always call it again "
        "instead of trusting an earlier result."
    )
    args_model = GetReservationOrdersArgs

    def run(self, ctx: ToolContext, args: GetReservationOrdersArgs) -> ToolResult:
        own_reservation(ctx, args.reservation_id)
        names = {i.id: i.name for i in ctx.backend.get_menu(MenuFilters(available_only=False))}
        orders = ctx.backend.list_reservation_orders(args.reservation_id)
        return ToolResult.success(
            {
                "orders": [
                    {
                        "order_id": o.id,
                        "menu_item_id": o.menu_item_id,
                        "name": names.get(o.menu_item_id, "unknown item"),
                        "quantity": o.quantity,
                    }
                    for o in orders
                ]
            }
        )
