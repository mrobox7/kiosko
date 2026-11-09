"""get_item: one dish with the questions the customer can answer about it."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.backend.models import Dish, MealOffer, OptionGroup
from app.menu.lookup import LookupFailed, find_question, resolve_dish
from app.menu.names import dish_name, normalise
from app.menu.questions import options_of, overview_of, question_of
from app.tools.contract import Tool, ToolContext, ToolResult, exactly_one


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


ESTIMATES = (
    "General estimates for the dish alone (no extras, meal side or drink), not official figures. "
    "Say so when answering."
)


def _facts(dish: Dish, info: str) -> dict[str, Any]:
    data: dict[str, Any] = {"dish_id": dish.id, "name": dish_name(dish.name)}
    if info == "nutrition":
        data["nutrition"] = dish.nutrition
    else:
        data["allergens"] = dish.allergens
        if not dish.allergens:
            data["allergens_note"] = "None listed. That does not mean it was checked allergen-free."
    data["note"] = ESTIMATES
    return data


def _meal(dish: Dish, size: str | None) -> MealOffer | None:
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


def _overview(dish: Dish, meal: MealOffer | None) -> dict[str, Any]:
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


def _opened(dish: Dish, group: OptionGroup, contains: str | None) -> dict[str, Any]:
    shown = group.options
    if contains is not None:
        words = normalise(contains).split()
        shown = [o for o in shown if all(w in normalise(o.name) for w in words)]
    data = {"name": dish_name(dish.name), "dish_id": dish.id}
    data |= question_of(group, options_of(group, shown))
    if contains is not None:
        data["of"] = len(group.options)  # how many the question has before narrowing
    return data
