"""add_to_order: put one dish, with its choices, on the customer's order."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.backend.errors import BackendError
from app.backend.models import Dish, Order
from app.menu.lookup import LookupFailed, find_options, resolve_dish
from app.menu.names import dish_name
from app.menu.questions import INLINE, options_of
from app.tools.backend_errors import refusal_for, settle
from app.tools.contract import Tool, ToolAborted, ToolContext, ToolResult, Update, exactly_one
from app.tools.order.cart import line_view


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
    args_model = AddToOrderArgs

    def run(self, ctx: ToolContext, args: AddToOrderArgs) -> ToolResult:
        try:
            dish, options = self._resolve(ctx, args)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        # The first dish starts the order. If the add then fails, the failure still carries the new
        # draft, so the chat keeps it and the next dish does not start another.
        started = None
        current = ctx.order
        if current is None:
            started = current = ctx.backend.create_order(ctx.outlet_code, ctx.customer_id)
        order_id, before = current.id, len(current.lines)
        body = {
            "product_id": dish.id,
            "quantity": args.quantity,
            "meal_size": args.meal_size,
            "options": options,
            "note": args.note,
        }

        def landed() -> Order | None:
            current = ctx.backend.get_order(order_id)
            return current if len(current.lines) > before else None

        try:
            order = settle(lambda: ctx.backend.add_order_line(order_id, body), landed=landed)
        except BackendError as exc:
            refusal = refusal_for(ctx, exc)
            if refusal is None or refusal.error is None:
                if started is None:
                    raise
                raise ToolAborted(exc, Update(order=started)) from exc
            if refusal.error.code == "incomplete":
                refusal.error.message = "Some choices are still needed."
                refusal.error.hint = self._ask(dish, exc)
            if started is not None and refusal.update is None:
                refusal.update = Update(order=started)
            return refusal
        added = max(order.lines, key=lambda dish: dish.id)  # ids only grow
        data = {
            "order_id": order.id,
            "added": line_view(added),
            "line_count": len(order.lines),
            "subtotal": order.subtotal,
            "gst": order.gst,
            "total": order.total,
        }
        return ToolResult(ok=True, data=data, changed=True, update=Update(order=order))

    @staticmethod
    def _ask(dish: Dish, exc: BackendError) -> str:
        """The question for the choices still missing, as it can be put to the customer: it names
        the dish and lists the options, so it needs nothing around it to make sense."""
        groups = {g.id: g for g in dish.option_groups}
        for meal in dish.meal_offers:
            groups |= {g.id: g for g in (meal.side, meal.drink) if g is not None}
        name = dish_name(dish.name)
        asked = []
        for issue in exc.missing:
            group = groups.get(issue.get("group_id") or -1)
            if group is None:
                continue
            if len(group.options) <= INLINE:
                asked.append(f"which {group.name}? {', '.join(options_of(group))}")
            else:
                asked.append(f"which {group.name}? There are {len(group.options)} options")
        if not asked:
            return f"For the {name}, a choice is still needed. What would you like?"
        return f"For the {name}, " + "; and ".join(asked) + "."

    @staticmethod
    def _resolve(ctx: ToolContext, args: AddToOrderArgs) -> tuple[Dish, list[dict[str, int]]]:
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
