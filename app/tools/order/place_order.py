"""place_order: confirm the customer's order."""

from pydantic import BaseModel

from app.backend.errors import BackendError
from app.backend.models import Order
from app.tools.backend_errors import refusal_for, reread, settle
from app.tools.contract import Tool, ToolContext, ToolResult, Update
from app.tools.order.cart import cart_view


class PlaceOrderArgs(BaseModel):
    """Arguments of place_order: none, it places this chat's order."""


class PlaceOrder(Tool[PlaceOrderArgs]):
    """Place the order."""

    name = "place_order"
    args_model = PlaceOrderArgs

    def run(self, ctx: ToolContext, args: PlaceOrderArgs) -> ToolResult:
        done = ctx.order
        if done is None:
            return ToolResult.failure("no_order", "There is no order yet.", "Add a dish first.")
        if ctx.placed:
            return ToolResult.failure(
                "already_placed",
                f"Order {done.id} is already placed as number {done.order_number}.",
                "Tell the customer the number. A new customer starts a new chat.",
            )
        order_id = done.id

        def landed() -> Order | None:
            current = ctx.backend.get_order(order_id)
            return current if current.status == "confirmed" else None

        try:
            order = settle(lambda: ctx.backend.confirm_order(order_id), landed=landed)
        except BackendError as exc:
            refusal = refusal_for(ctx, exc)
            if refusal is None or refusal.error is None:
                raise
            if refusal.error.code in ("price_changed", "unavailable"):
                refusal.update = reread(ctx)  # the server re-priced the lines: show them as now
                fresh = refusal.update.order if refusal.update else None
                if refusal.error.code == "price_changed" and fresh is not None:
                    refusal.error.hint = (
                        f"The order is still open at the new prices: total now "
                        f"{fresh.total}. Tell the customer and place it again only "
                        "after they agree."
                    )
            return refusal
        # Confirmed: the chat is over.
        data = {**cart_view(order), "order_number": order.order_number}
        return ToolResult(ok=True, data=data, changed=True, update=Update(order=order))
