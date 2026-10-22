"""remove_from_order: take one line off the customer's order."""

from pydantic import BaseModel, Field, model_validator

from app.backend.models import DriveThruOrder
from app.domain.results import ToolResult
from app.menu.names import dish_name
from app.tools.base import Tool, ToolContext
from app.tools.cart import cart_view, pick_line
from app.tools.menu_lookup import LookupFailed, exactly_one
from app.tools.recover import settle


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
    description = (
        "Remove a line from the customer's order: name the dish (`dish`) or send its `line_id` "
        "from the order. If the same dish is on the order twice, the reply lists the lines so you "
        "can ask which. The reply shows the lines left and the new totals. To change how many, "
        "use change_quantity; to change anything else, remove the line and add it again."
    )
    args_model = RemoveFromOrderArgs
    mutating = True
    shown_in_order = True

    def run(self, ctx: ToolContext, args: RemoveFromOrderArgs) -> ToolResult:
        try:
            line = pick_line(ctx, args.dish, args.line_id)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        order_id = ctx.order.latest.id if ctx.order.latest else 0

        def landed() -> DriveThruOrder | None:
            current = ctx.backend.get_order(order_id)
            return current if all(i.id != line.id for i in current.lines) else None

        order = settle(lambda: ctx.backend.remove_order_line(order_id, line.id), landed=landed)
        ctx.order.latest = order
        data = {
            **cart_view(order),
            "removed": {
                "line_id": line.id,
                "name": dish_name(line.name),
                "quantity": line.quantity,
            },
        }
        return ToolResult(ok=True, data=data, changed=True)

    def compact(self, result: ToolResult, args: RemoveFromOrderArgs) -> str:
        if not result.ok:
            code = result.error.code if result.error else "error"
            label = f"line {args.line_id}" if args.line_id is not None else repr(args.dish)
            return f"{label}: not removed ({code})"
        d = result.data
        gone = d["removed"]
        return (
            f"order {d['order_id']}: removed {gone['quantity']}x {gone['name']} "
            f"(line {gone['line_id']}), total {d['total']}"
        )
