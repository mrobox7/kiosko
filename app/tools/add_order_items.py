"""add_order_items: order dishes against a booking."""

from typing import Any

from pydantic import BaseModel, Field

from app.backend.errors import BackendError, BackendUnavailable
from app.domain.results import ALLERGY_CONFLICT, BACKEND_REJECTED, ToolError, ToolResult
from app.domain.state import LedgerEntry
from app.memory.schema import ALLERGEN_MENU_TAG
from app.memory.service import MemoryService
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
        # Allergy guard: read allergies fresh (never a cached copy), so an allergy stated
        # earlier in this same turn applies. If this read fails the order is refused.
        allergies = MemoryService(ctx.backend).read_preferences(ctx.require_customer()).allergies
        watched = {ALLERGEN_MENU_TAG[a]: a for a in allergies if a in ALLERGEN_MENU_TAG}
        unchecked = [a for a in allergies if a not in ALLERGEN_MENU_TAG]
        added: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        writes: list[LedgerEntry] = []
        for index, item in enumerate(args.items):
            try:
                if watched:
                    dish = ctx.backend.get_menu_item(item.menu_item_id)
                    hit = next((a for tag, a in watched.items() if tag in dish.tags), None)
                    if hit:
                        failed.append(
                            {
                                "menu_item_id": item.menu_item_id,
                                "code": ALLERGY_CONFLICT,
                                "allergen": hit,
                                "reason": f"{dish.name} contains {hit}, which is on this "
                                "customer's allergy list. It was not ordered.",
                            }
                        )
                        continue
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
            writes.append(ctx.ledger(self.name, "added", order.id))
        data: dict[str, Any] = {"added": added, "failed": failed}
        if unchecked:
            data["unchecked_allergies"] = unchecked
            data["note"] = (
                f"The menu has no data for {', '.join(unchecked)}; tell the customer and "
                "advise confirming with staff."
            )
        if added:
            return ToolResult(ok=True, data=data, writes=writes)
        blocked = any(f.get("code") == ALLERGY_CONFLICT for f in failed)
        return ToolResult(
            ok=False,
            data=data,
            error=ToolError(
                code=ALLERGY_CONFLICT if blocked else BACKEND_REJECTED,
                message="No items were added.",
                hint="Offer alternatives without the allergen." if blocked else None,
            ),
        )

    def compact(self, result: ToolResult, args: AddOrderItemsArgs) -> str:
        # The order ids are what remove_order_item needs later.
        orders = [
            f"order {a['order_id']} item #{a['menu_item_id']} x{a['quantity']}"
            for a in (result.data["added"] if isinstance(result.data, dict) else [])
        ]
        if orders:
            line = f"added to booking #{args.reservation_id}: " + "; ".join(orders)
        else:
            line = super().compact(result, args)
        failed = result.data["failed"] if isinstance(result.data, dict) else []
        refused = [
            f"item #{f['menu_item_id']} ({f['allergen']} allergy)"
            if f.get("code") == ALLERGY_CONFLICT
            else f"item #{f['menu_item_id']} (rejected)"
            for f in failed
        ]
        return f"{line}; not added: {', '.join(refused)}" if refused else line
