"""get_menu: the outlet's menu, narrowed by category, veg, price, nutrition or allergen."""

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.backend.models import MenuDish
from app.domain.results import ToolResult
from app.domain.state import Allergen
from app.menu.names import dish_name
from app.tools.base import Tool, ToolContext

PAGE = 10

# The menu's categories (backend/seed/seed.json); a test keeps this list in step with the seed.
Category = Literal[
    "burgers", "wraps", "fries-sides", "meals", "mccaf", "beverages", "desserts", "condiments"
]

ESTIMATES = (
    "Nutrition and allergen data are general estimates. 'Without' means none is listed, not that "
    "it was checked free of it."
)


class GetMenuArgs(BaseModel):
    """Arguments of get_menu."""

    category: Category | None = None
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
    """Browse the menu."""

    name = "get_menu"
    description = (
        "Search what the outlet is selling now. With no arguments it lists the categories and how "
        "many dishes each has. Otherwise it lists the dishes that match every filter you send: "
        "`category`, `veg` (true veg only, false non-veg only), `min_price` and `max_price`, "
        "`kind` (a `single` dish or a `combo`), `without` (an allergen), `min_protein` (grams), "
        "`max_calories` (kcal), `bestseller`. Menu order unless `sort` is given. 10 per page; "
        "`more` says how many are left, so ask for the next `page`. Use the filters instead of "
        "reading the whole menu; never offer anything this does not return."
    )
    args_model = GetMenuArgs

    def run(self, ctx: ToolContext, args: GetMenuArgs) -> ToolResult:
        menu = ctx.menu.dishes
        if not args.model_fields_set - {"page"}:
            counts = Counter(dish.category for dish in menu)  # keeps menu order
            return ToolResult.success(
                {"categories": [{"category": c, "dishes": n} for c, n in counts.items()]}
            )
        shown = [d for d in menu if _wanted(d, args)]
        if args.sort:
            shown = _sorted(shown, args.sort)
        start = (args.page - 1) * PAGE
        data: dict[str, Any] = {"dishes": [_entry(d, args) for d in shown[start : start + PAGE]]}
        if len(shown) > start + PAGE:
            data["more"] = len(shown) - start - PAGE
        if _uses_estimates(args):
            data["note"] = ESTIMATES
        return ToolResult.success(data)

    def compact(self, result: ToolResult, args: GetMenuArgs) -> str:
        if not result.ok:
            code = result.error.code if result.error else "error"
            return f"menu: failed ({code})"
        if "categories" in result.data:
            listed = ", ".join(f"{c['category']} {c['dishes']}" for c in result.data["categories"])
            return f"menu categories: {listed}"
        filters = [
            f"category {args.category}" if args.category else "",
            "veg" if args.veg is True else "non-veg" if args.veg is False else "",
            f"min {args.min_price:g}" if args.min_price else "",
            f"max {args.max_price:g}" if args.max_price else "",
            args.kind or "",
            f"without {args.without}" if args.without else "",
            f"protein >= {args.min_protein:g}g" if args.min_protein else "",
            f"calories <= {args.max_calories:g}" if args.max_calories else "",
            "bestsellers" if args.bestseller else "",
            args.sort.replace("_", " ") if args.sort else "",
            f"page {args.page}" if args.page > 1 else "",
        ]
        asked = ", ".join(f for f in filters if f)
        dishes = result.data["dishes"]
        if not dishes:
            return f"menu ({asked}): nothing"
        listed = ", ".join(f"{i['name']} (dish {i['dish_id']})" for i in dishes[:5])
        return f"menu ({asked}): {listed}" + (", ..." if len(dishes) > 5 else "")


def _protein(dish: MenuDish) -> float | None:
    return dish.nutrition.get("protein_g")


def _calories(dish: MenuDish) -> float | None:
    return dish.nutrition.get("calories_kcal")


def _wanted(dish: MenuDish, args: GetMenuArgs) -> bool:
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


def _calories_or_last(dish: MenuDish) -> float:
    calories = _calories(dish)  # 0 is a real figure, not a missing one
    return float("inf") if calories is None else calories


def _sorted(dishes: list[MenuDish], how: str) -> list[MenuDish]:
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


def _entry(dish: MenuDish, args: GetMenuArgs) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "dish_id": dish.id,
        "name": dish_name(dish.name),
        "price": dish.base_price,
        "veg": dish.veg == "veg",
        "combo": dish.kind == "combo",
    }
    # The figure that was asked about is shown, so the model can say it without another call.
    if args.min_protein is not None or args.sort == "most_protein_first":
        entry["protein_g"] = _protein(dish)
    if args.max_calories is not None or args.sort == "fewest_calories_first":
        entry["calories_kcal"] = _calories(dish)
    return entry
