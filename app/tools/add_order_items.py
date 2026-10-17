"""add_order_items: order dishes against a booking."""

from typing import Any

from pydantic import BaseModel, Field

from app.backend.errors import BackendError, BackendUnavailable
from app.domain.results import BACKEND_REJECTED, ToolError, ToolResult
from app.domain.state import LedgerEntry
from app.tools.base import Tool, ToolContext
from app.tools.checks import own_reservation


class OrderItem(BaseModel):
    """One dish and how many."""

    menu_item_id: int = Field(description="Item id from list_menu")
    quantity: int = Field(default=1, ge=1)


class AddOrderItemsArgs(BaseModel):
    """Arguments of add_order_items."""

    reservation_id: int
    items: list[OrderItem] = Field(min_length=1, max_length=10)


class AddOrderItems(Tool[AddOrderItemsArgs]):
    """Add dishes to a reservation."""

    name = "add_order_items"
    description = (
        "Use to order dishes against a reservation. Look up item ids with list_menu first. "
        "Items are added one by one; the result lists what was added and what failed and why."
    )
    args_model = AddOrderItemsArgs
    mutating = True

    def run(self, ctx: ToolContext, args: AddOrderItemsArgs) -> ToolResult:
        own_reservation(ctx, args.reservation_id)
        added: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        writes: list[LedgerEntry] = []
        for index, item in enumerate(args.items):
            try:
                order = ctx.backend.add_order(args.reservation_id, item.menu_item_id, item.quantity)
            except BackendUnavailable as exc:
                # Stop here, but keep the ledger of what already went through.
                for rest in args.items[index:]:
                    failed.append({"menu_item_id": rest.menu_item_id, "reason": exc.message})
                break
            except BackendError as exc:
                failed.append({"menu_item_id": item.menu_item_id, "reason": exc.message})
                continue
            added.append(
                {
                    "order_id": order.id,
                    "menu_item_id": order.menu_item_id,
                    "quantity": order.quantity,
                }
            )
            writes.append(
                ctx.ledger(
                    self.name,
                    "added",
                    order.id,
                    f"Added item #{order.menu_item_id} x{order.quantity}"
                    f" to reservation #{args.reservation_id}",
                )
            )
        data = {"added": added, "failed": failed}
        if added:
            return ToolResult(ok=True, data=data, writes=writes)
        return ToolResult(
            ok=False,
            data=data,
            error=ToolError(code=BACKEND_REJECTED, message="No items were added."),
        )
