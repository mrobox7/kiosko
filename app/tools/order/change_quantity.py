"""change_quantity: change how many of a line the customer wants."""

from pydantic import BaseModel, Field, model_validator

from app.menu.lookup import LookupFailed
from app.tools.backend_errors import settle
from app.tools.contract import Tool, ToolContext, ToolResult, Update, exactly_one
from app.tools.order.cart import cart_view, pick_line


class ChangeQuantityArgs(BaseModel):
    """Arguments of change_quantity."""

    dish: str | None = Field(default=None, max_length=100)
    line_id: int | None = None
    quantity: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def _dish_or_line(self) -> ChangeQuantityArgs:
        exactly_one(self.dish, self.line_id, "dish / line_id")
        return self


class ChangeQuantity(Tool[ChangeQuantityArgs]):
    """Change how many of a line."""

    name = "change_quantity"
    args_model = ChangeQuantityArgs

    def run(self, ctx: ToolContext, args: ChangeQuantityArgs) -> ToolResult:
        try:
            line = pick_line(ctx, args.dish, args.line_id)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        order_id = ctx.order.id if ctx.order else 0
        # Setting a quantity twice is the same as setting it once, so a lost reply is just resent.
        order = settle(
            lambda: ctx.backend.set_line_quantity(order_id, line.id, args.quantity),
            landed=lambda: None,
        )
        data = {**cart_view(order), "changed_line_id": line.id}
        return ToolResult(ok=True, data=data, changed=True, update=Update(order=order))
