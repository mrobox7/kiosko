"""change_quantity: change how many of a line the customer wants."""

from pydantic import BaseModel, Field, model_validator

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.cart import cart_view, pick_line
from app.tools.menu_lookup import LookupFailed, exactly_one
from app.tools.recover import settle


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
    description = (
        "Change how many of a line the customer wants: name the dish (`dish`) or send its "
        "`line_id`, and the new `quantity` (1 to 20; to take it off, use remove_from_order). Its "
        "choices stay as they were. The reply shows every line and the new totals."
    )
    args_model = ChangeQuantityArgs
    mutating = True
    shown_in_order = True

    def run(self, ctx: ToolContext, args: ChangeQuantityArgs) -> ToolResult:
        try:
            line = pick_line(ctx, args.dish, args.line_id)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        order_id = ctx.order.latest.id if ctx.order.latest else 0
        # Setting a quantity twice is the same as setting it once, so a lost reply is just resent.
        order = settle(
            lambda: ctx.backend.set_line_quantity(order_id, line.id, args.quantity),
            landed=lambda: None,
        )
        ctx.order.latest = order
        data = {**cart_view(order), "changed_line_id": line.id}
        return ToolResult(ok=True, data=data, changed=True)

    def compact(self, result: ToolResult, args: ChangeQuantityArgs) -> str:
        if not result.ok:
            code = result.error.code if result.error else "error"
            label = f"line {args.line_id}" if args.line_id is not None else repr(args.dish)
            return f"{label}: quantity not changed ({code})"
        d = result.data
        line = next(x for x in d["lines"] if x["line_id"] == d["changed_line_id"])
        return (
            f"order {d['order_id']}: line {line['line_id']} {line['name']} now "
            f"{line['quantity']}x, total {d['total']}"
        )
