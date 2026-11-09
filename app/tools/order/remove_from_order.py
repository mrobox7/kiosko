"""remove_from_order: take one line off the customer's order."""

from pydantic import BaseModel, Field, model_validator

from app.backend.models import Order
from app.menu.lookup import LookupFailed
from app.menu.names import dish_name
from app.tools.backend_errors import settle
from app.tools.contract import Tool, ToolContext, ToolResult, Update, exactly_one
from app.tools.order.cart import cart_view, pick_line


class RemoveFromOrderArgs(BaseModel):
    """Arguments of remove_from_order."""

    dish: str | None = Field(default=None, max_length=100)
    line_id: int | None = None

    @model_validator(mode="after")
    def _dish_or_line(self) -> RemoveFromOrderArgs:
        exactly_one(self.dish, self.line_id, "dish / line_id")
        return self


class RemoveFromOrder(Tool[RemoveFromOrderArgs]):
    """Remove one line from the order."""

    name = "remove_from_order"
    args_model = RemoveFromOrderArgs

    def run(self, ctx: ToolContext, args: RemoveFromOrderArgs) -> ToolResult:
        try:
            line = pick_line(ctx, args.dish, args.line_id)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        order_id = ctx.order.id if ctx.order else 0

        def landed() -> Order | None:
            current = ctx.backend.get_order(order_id)
            return current if all(i.id != line.id for i in current.lines) else None

        order = settle(lambda: ctx.backend.remove_order_line(order_id, line.id), landed=landed)
        data = {
            **cart_view(order),
            "removed": {
                "line_id": line.id,
                "name": dish_name(line.name),
                "quantity": line.quantity,
            },
        }
        return ToolResult(ok=True, data=data, changed=True, update=Update(order=order))
