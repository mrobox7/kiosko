"""place_order: confirm the customer's order."""

from pydantic import BaseModel

from app.backend.errors import BackendError
from app.backend.models import DriveThruOrder
from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.cart import cart_view, refusal_for, resync
from app.tools.recover import settle


class PlaceOrderArgs(BaseModel):
    """Arguments of place_order: none, it places this chat's order."""


class PlaceOrder(Tool[PlaceOrderArgs]):
    """Place the order."""

    name = "place_order"
    description = (
        "Place the customer's order after they have agreed to the dishes and the total. The reply "
        "has the `order_number` to call out. This ends the chat: nothing can be added afterwards. "
        "If it fails the order stays open; the error says what to do."
    )
    args_model = PlaceOrderArgs
    mutating = True
    shown_in_order = True

    def run(self, ctx: ToolContext, args: PlaceOrderArgs) -> ToolResult:
        if ctx.order.order_id is None:
            return ToolResult.failure("no_order", "There is no order yet.", "Add a dish first.")
        if (done := ctx.order.latest) is not None and ctx.order.placed:
            return ToolResult.failure(
                "already_placed",
                f"Order {done.id} is already placed as number {done.order_number}.",
                "Tell the customer the number. A new customer starts a new chat.",
            )
        order_id = ctx.order.order_id

        def landed() -> DriveThruOrder | None:
            current = ctx.backend.get_order(order_id)
            return current if current.status == "confirmed" else None

        try:
            order = settle(lambda: ctx.backend.confirm_order(order_id), landed=landed)
        except BackendError as exc:
            refusal = refusal_for(ctx, exc)
            if refusal is None or refusal.error is None:
                raise
            if refusal.error.code in ("price_changed", "unavailable"):
                resync(ctx)  # the server re-priced the lines: show them as they now are
                if refusal.error.code == "price_changed" and ctx.order.latest is not None:
                    refusal.error.hint = (
                        f"The order is still open at the new prices: total now "
                        f"{ctx.order.latest.total}. Tell the customer and place it again only "
                        "after they agree."
                    )
            return refusal
        ctx.order.latest = order  # confirmed: the chat is over
        data = {**cart_view(order), "order_number": order.order_number}
        return ToolResult(ok=True, data=data, changed=True)

    def compact(self, result: ToolResult, args: PlaceOrderArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        d = result.data
        return f"order {d['order_id']} placed as number {d['order_number']}, total {d['total']}"
