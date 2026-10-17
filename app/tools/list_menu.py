"""list_menu: dishes, prices and dietary options."""

from typing import Literal

from pydantic import BaseModel, Field

from app.backend.models import MenuFilters
from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext

Tag = Literal["vegetarian", "vegan", "contains-nuts", "contains-dairy"]
Category = Literal["starter", "main", "dessert"]
MAX_ITEMS = 30


class ListMenuArgs(BaseModel):
    """Arguments of list_menu. All optional."""

    category: Category | None = Field(default=None, description="Menu section")
    tags_any: list[Tag] = Field(default_factory=list, description="Items having ANY of these tags")
    tags_all: list[Tag] = Field(default_factory=list, description="Items having ALL of these tags")
    exclude_tags: list[Tag] = Field(
        default_factory=list, description="Drop items having ANY of these tags"
    )
    max_price: float | None = Field(default=None, description="Maximum price per item")
    available_only: bool = Field(default=True, description="Hide unavailable items")


class ListMenu(Tool[ListMenuArgs]):
    """Read the menu with optional filters."""

    name = "list_menu"
    description = (
        "Use for any question about dishes, prices or dietary options. "
        "Item ids from this tool are required for ordering."
    )
    args_model = ListMenuArgs

    def run(self, ctx: ToolContext, args: ListMenuArgs) -> ToolResult:
        items = ctx.backend.get_menu(MenuFilters.model_validate(args.model_dump()))
        data: dict[str, object] = {
            "items": [
                i.model_dump(include={"id", "name", "price", "category", "tags", "available"})
                for i in items[:MAX_ITEMS]
            ]
        }
        if len(items) > MAX_ITEMS:
            data["note"] = f"Showing {MAX_ITEMS} of {len(items)} items; narrow the filters."
        return ToolResult.success(data)

    def compact(self, result: ToolResult, args: ListMenuArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        dishes = []
        for item in result.data["items"]:
            flags = [t.removeprefix("contains-") for t in item["tags"] if t.startswith("contains-")]
            if not item["available"]:
                flags.append("unavailable")
            suffix = f" ({', '.join(flags)})" if flags else ""
            dishes.append(f"{item['id']} {item['name']} {item['price']:g}{suffix}")
        return f"{len(dishes)} dishes: " + "; ".join(dishes) if dishes else "no dishes matched"
