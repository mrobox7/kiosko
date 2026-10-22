"""get_item: one dish with the questions the customer can answer about it."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.backend.models import MenuDish, MenuMealOffer, MenuOptionGroup
from app.domain.results import ToolResult
from app.menu.names import dish_name, normalise
from app.tools.base import Tool, ToolContext
from app.tools.menu_lookup import LookupFailed, exactly_one, find_question, resolve_dish
from app.tools.questions import options_of, overview_of, question_of


class GetItemArgs(BaseModel):
    """Arguments of get_item."""

    dish: str | None = Field(default=None, max_length=100)
    dish_id: int | None = None
    meal_size: Literal["Medium", "Large"] | None = None
    question: str | None = Field(default=None, max_length=100)
    contains: str | None = Field(default=None, max_length=50)
    info: Literal["nutrition", "allergens"] | None = None

    @model_validator(mode="after")
    def _valid(self) -> GetItemArgs:
        exactly_one(self.dish, self.dish_id, "dish / dish_id")
        if self.info is not None and (self.question or self.meal_size or self.contains):
            raise ValueError("`info` is asked on its own: send it with only the dish")
        if self.contains is not None and self.question is None:
            raise ValueError("`contains` narrows one question: send `question` with it")
        return self


class GetItem(Tool[GetItemArgs]):
    """Look at one dish."""

    name = "get_item"
    description = (
        "What the customer can choose on one dish: name it as on the menu (`dish`) or by "
        "`dish_id`. Send `meal_size` to also get the side and drink questions of that meal. Send "
        "`question` to get the full options of one question, and `contains` with it to keep only "
        'options with that word ("coke"), which also tells you whether the outlet has something. '
        "Use it before offering choices; never offer an option it does not list. For nutrition "
        "(calories, protein, fat, carbs, sugar, sodium) or `allergens`, send `info` on its own "
        "with the dish."
    )
    args_model = GetItemArgs

    def run(self, ctx: ToolContext, args: GetItemArgs) -> ToolResult:
        try:
            dish = resolve_dish(ctx.menu, args.dish, args.dish_id)
            if args.info is not None:
                return ToolResult.success(_facts(dish, args.info))
            if args.question is not None:
                group = find_question(dish, args.question, args.meal_size)
                return ToolResult.success(_opened(dish, group, args.contains))
            meal = _meal(dish, args.meal_size)
        except LookupFailed as problem:
            return ToolResult.failure(problem.code, problem.message, problem.hint)
        return ToolResult.success(_overview(dish, meal))

    def compact(self, result: ToolResult, args: GetItemArgs) -> str:
        label = f"dish {args.dish_id}" if args.dish_id is not None else repr(args.dish)
        if not result.ok:
            code = result.error.code if result.error else "error"
            return f"{label}: not shown ({code})"
        d = result.data
        if args.info:
            return f"{d['name']}: {args.info}"
        if "options" in d:
            return f"{d['name']}: question {d['question']!r}, {len(d['options'])} options"
        return f"{d['name']} (dish {d['dish_id']}): {len(d.get('questions', []))} questions"


ESTIMATES = (
    "General estimates for the dish alone (no extras, meal side or drink), not official figures. "
    "Say so when answering."
)


def _facts(dish: MenuDish, info: str) -> dict[str, Any]:
    data: dict[str, Any] = {"dish_id": dish.id, "name": dish_name(dish.name)}
    if info == "nutrition":
        data["nutrition"] = dish.nutrition
    else:
        data["allergens"] = dish.allergens
        if not dish.allergens:
            data["allergens_note"] = "None listed. That does not mean it was checked allergen-free."
    data["note"] = ESTIMATES
    return data


def _meal(dish: MenuDish, size: str | None) -> MenuMealOffer | None:
    """The meal offer of the size asked for, or None when no size was asked for."""
    if size is None:
        return None
    for offer in dish.meal_offers:
        if offer.size == size:
            return offer
    sold = " and ".join(o.size for o in dish.meal_offers)
    raise LookupFailed(
        "no_such_meal",
        f"{dish_name(dish.name)} has no {size} meal",
        f"Meal sizes for it: {sold}" if sold else "It cannot be made a meal",
    )


def _overview(dish: MenuDish, meal: MenuMealOffer | None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dish_id": dish.id,
        "name": dish_name(dish.name),
        "price": dish.base_price,
        "veg": dish.veg == "veg",
    }
    if dish.description:
        data["description"] = dish.description
    groups = list(dish.option_groups)
    if meal is not None:
        groups += [g for g in (meal.side, meal.drink) if g is not None]
    data["questions"] = [overview_of(g) for g in groups]
    if dish.meal_offers:
        data["meals"] = [{"size": o.size, "extra_price": o.price_delta} for o in dish.meal_offers]
    return data


def _opened(dish: MenuDish, group: MenuOptionGroup, contains: str | None) -> dict[str, Any]:
    shown = group.options
    if contains is not None:
        words = normalise(contains).split()
        shown = [o for o in shown if all(w in normalise(o.name) for w in words)]
    data = {"name": dish_name(dish.name), "dish_id": dish.id}
    data |= question_of(group, options_of(group, shown))
    if contains is not None:
        data["of"] = len(group.options)  # how many the question has before narrowing
    return data
