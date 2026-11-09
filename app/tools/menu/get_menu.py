"""get_menu: the outlet's menu, found by name or narrowed by category, veg, price, nutrition or
allergen."""

from collections import Counter
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.backend.models import Allergen, Dish
from app.menu.fuzzy import LOW, rank
from app.menu.names import dish_name
from app.tools.contract import Tool, ToolContext, ToolResult

PAGE = 10

# The menu's categories (backend/seed/seed.json); a test keeps this list in step with the seed.
CategorySlug = Literal[
    "burgers", "wraps", "fries-sides", "meals", "mccaf", "beverages", "desserts", "condiments"
]

ESTIMATES = (
    "Nutrition and allergen data are general estimates. 'Without' means none is listed, not that "
    "it was checked free of it."
)


class GetMenuArgs(BaseModel):
    """Arguments of get_menu."""

    text: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="A dish name, or words from one ('pizza', 'mc aloo tikki'). Best match first.",
    )
    category: CategorySlug | None = None
    veg: bool | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, gt=0)
    kind: Literal["single", "combo"] | None = None
    without: Allergen | None = None
    min_protein: float | None = Field(default=None, gt=0)
    max_calories: float | None = Field(default=None, gt=0)
    bestseller: Literal[True] | None = None
    sort: (
        Literal["cheapest_first", "priciest_first", "most_protein_first", "fewest_calories_first"]
        | None
    ) = None
    page: int = Field(default=1, ge=1)


class GetMenu(Tool[GetMenuArgs]):
    """Browse or search the menu."""

    name = "get_menu"
    args_model = GetMenuArgs

    def run(self, ctx: ToolContext, args: GetMenuArgs) -> ToolResult:
        menu = ctx.menu.dishes
        if not args.model_fields_set - {"page"}:
            return ToolResult.success({"categories": _categories(menu)})
        shown = [d for d in menu if _wanted(d, args)]
        scores: dict[int, float] = {}
        if args.text:
            ranked = [m for m in rank(args.text, shown) if m.score >= LOW]
            if not ranked:  # a real answer, not an error: nothing is named like that
                return ToolResult.success(
                    {
                        "dishes": [],
                        "note": f"No dish is named like '{args.text}'. If it is a kind of food, "
                        "try a section from `categories`.",
                        "categories": _categories(menu),
                    }
                )
            scores = {m.dish.id: m.score for m in ranked}
            shown = [m.dish for m in ranked]  # best match first
        if args.sort:
            shown = _sorted(shown, args.sort)
        start = (args.page - 1) * PAGE
        data: dict[str, Any] = {
            "dishes": [_entry(d, args, scores) for d in shown[start : start + PAGE]]
        }
        if len(shown) > start + PAGE:
            data["more"] = len(shown) - start - PAGE
        if _uses_estimates(args):
            data["note"] = ESTIMATES
        return ToolResult.success(data)


def _categories(menu: Sequence[Dish]) -> list[dict[str, Any]]:
    """Each section with how many dishes it has, in menu order."""
    counts = Counter(dish.category for dish in menu)
    return [{"category": c, "dishes": n} for c, n in counts.items()]


def _protein(dish: Dish) -> float | None:
    return dish.nutrition.get("protein_g")


def _calories(dish: Dish) -> float | None:
    return dish.nutrition.get("calories_kcal")


def _wanted(dish: Dish, args: GetMenuArgs) -> bool:
    protein, calories = _protein(dish), _calories(dish)
    return (
        (args.category is None or dish.category == args.category)
        and (args.veg is None or (dish.veg == "veg") == args.veg)
        and (args.min_price is None or dish.base_price >= args.min_price)
        and (args.max_price is None or dish.base_price <= args.max_price)
        and (args.kind is None or dish.kind == ("item" if args.kind == "single" else "combo"))
        and (args.without is None or args.without not in dish.allergens)
        # a dish with no figure cannot be said to meet a limit on it
        and (args.min_protein is None or (protein is not None and protein >= args.min_protein))
        and (args.max_calories is None or (calories is not None and calories <= args.max_calories))
        and (args.bestseller is None or "bestseller" in dish.tags)
    )


def _calories_or_last(dish: Dish) -> float:
    calories = _calories(dish)  # 0 is a real figure, not a missing one
    return float("inf") if calories is None else calories


def _sorted(dishes: list[Dish], how: str) -> list[Dish]:
    """Stable, so dishes that tie keep menu order. A dish with no figure goes last."""
    if how == "most_protein_first":
        return sorted(dishes, key=lambda d: -(_protein(d) or 0))
    if how == "fewest_calories_first":
        return sorted(dishes, key=_calories_or_last)
    return sorted(dishes, key=lambda d: d.base_price, reverse=how == "priciest_first")


def _uses_estimates(args: GetMenuArgs) -> bool:
    return (
        args.without is not None
        or args.min_protein is not None
        or args.max_calories is not None
        or args.sort in ("most_protein_first", "fewest_calories_first")
    )


def _entry(dish: Dish, args: GetMenuArgs, scores: dict[int, float]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "dish_id": dish.id,
        "name": dish_name(dish.name),
        "price": dish.base_price,
        "veg": dish.veg == "veg",
        "combo": dish.kind == "combo",
    }
    if dish.id in scores:
        entry["match"] = round(scores[dish.id], 2)  # how well the name fits what was asked
    # The figure that was asked about is shown, so the model can say it without another call.
    if args.min_protein is not None or args.sort == "most_protein_first":
        entry["protein_g"] = _protein(dish)
    if args.max_calories is not None or args.sort == "fewest_calories_first":
        entry["calories_kcal"] = _calories(dish)
    return entry
