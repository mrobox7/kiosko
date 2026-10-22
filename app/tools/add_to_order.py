"""add_to_order: put one dish, with its choices, on the customer's order."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.backend.errors import BackendError
from app.backend.models import DriveThruOrder, MenuDish
from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.cart import line_view, refusal_for
from app.tools.menu_lookup import LookupFailed, exactly_one, find_options, resolve_dish
from app.tools.questions import INLINE, options_of
from app.tools.recover import settle


class OptionPick(BaseModel):
    """A choice, by name or by id."""

    name: str | None = Field(default=None, max_length=100)
    option_id: int | None = None
    qty: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="after")
    def _name_or_id(self) -> OptionPick:
        exactly_one(self.name, self.option_id, "name / option_id")
        return self


class AddToOrderArgs(BaseModel):
    """Arguments of add_to_order."""

    dish: str | None = Field(default=None, max_length=100)
    dish_id: int | None = None
    quantity: int = Field(default=1, ge=1, le=20)
    meal_size: Literal["Medium", "Large"] | None = None
    options: list[OptionPick] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _dish_or_id(self) -> AddToOrderArgs:
        exactly_one(self.dish, self.dish_id, "dish / dish_id")
        return self


class AddToOrder(Tool[AddToOrderArgs]):
    """Add one dish to the order."""

    name = "add_to_order"
    description = (
        "Add one dish to the customer's order; the first call starts the order. Name the dish as "
        "on the menu (`dish`) or send its `dish_id` from get_menu, and name each choice "
        "(`options`). Choices that belong to a meal (its side, its drink) need `meal_size`. The "
        "reply shows the new line and the order's totals. If it fails nothing was added: the "
        "error lists the nearest names or the questions to ask the customer, or what to change."
    )
    args_model = AddToOrderArgs
    mutating = True
    shown_in_order = True

    def run(self, ctx: ToolContext, args: AddToOrderArgs) -> ToolResult:
        try:
            dish, options = self._resolve(ctx, args)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        if ctx.order.latest is None:
            ctx.order.latest = ctx.backend.create_order(ctx.outlet_code, ctx.customer_id)
        order_id, before = ctx.order.latest.id, len(ctx.order.latest.lines)
        body = {
            "product_id": dish.id,
            "quantity": args.quantity,
            "meal_size": args.meal_size,
            "options": options,
            "note": args.note,
        }

        def landed() -> DriveThruOrder | None:
            current = ctx.backend.get_order(order_id)
            return current if len(current.lines) > before else None

        try:
            order = settle(lambda: ctx.backend.add_order_line(order_id, body), landed=landed)
        except BackendError as exc:
            refusal = refusal_for(ctx, exc)
            if refusal is None or refusal.error is None:
                raise
            if refusal.error.code == "incomplete":
                asked = self._ask(dish, exc)
                if asked is not None:  # the hint now holds the questions: do not say them twice
                    refusal.error.message = "Some choices are still needed."
                    refusal.error.hint = asked
            return refusal
        ctx.order.latest = order
        added = max(order.lines, key=lambda dish: dish.id)  # ids only grow
        data = {
            "order_id": order.id,
            "added": line_view(added),
            "line_count": len(order.lines),
            "subtotal": order.subtotal,
            "gst": order.gst,
            "total": order.total,
        }
        return ToolResult(ok=True, data=data, changed=True)

    @staticmethod
    def _ask(dish: MenuDish, exc: BackendError) -> str | None:
        """The unanswered questions with their options, so the model can ask them in one go."""
        groups = {g.id: g for g in dish.option_groups}
        for meal in dish.meal_offers:
            groups |= {g.id: g for g in (meal.side, meal.drink) if g is not None}
        asked = []
        for issue in exc.missing:
            group = groups.get(issue.get("group_id") or -1)
            if group is None:
                continue
            if len(group.options) <= INLINE:
                asked.append(f"{group.name}: {', '.join(options_of(group))}")
            else:
                asked.append(
                    f"{group.name}: {len(group.options)} options, open it with get_item question"
                )
        return f"Nothing was added. Ask the customer: {'; '.join(asked)}." if asked else None

    @staticmethod
    def _resolve(ctx: ToolContext, args: AddToOrderArgs) -> tuple[MenuDish, list[dict[str, int]]]:
        """The dish and the option ids, from the menu the agent holds: no request is made."""
        dish = resolve_dish(ctx.menu, args.dish, args.dish_id)
        named = [pick.name for pick in args.options if pick.name is not None]
        ids = {}
        if named:
            ids = dict(zip(named, find_options(dish, named, args.meal_size), strict=True))
        options: list[dict[str, int]] = []
        for pick in args.options:
            option_id = pick.option_id if pick.name is None else ids[pick.name]
            assert option_id is not None  # the arguments allow a name or an id, never neither
            options.append({"option_id": option_id, "qty": pick.qty})
        return dish, options

    def compact(self, result: ToolResult, args: AddToOrderArgs) -> str:
        if not result.ok:
            code = result.error.code if result.error else "error"
            label = f"dish {args.dish_id}" if args.dish_id is not None else repr(args.dish)
            return f"{label}: not added ({code})"
        d = result.data
        dish = d["added"]
        return (
            f"order {d['order_id']}: added {dish['quantity']}x {dish['name']} "
            f"(line {dish['line_id']}), total {d['total']}"
        )
