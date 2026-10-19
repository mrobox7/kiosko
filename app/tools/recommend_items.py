"""recommend_items: dishes to suggest, filtered by the customer's saved diet and allergies."""

from pydantic import BaseModel

from app.backend.models import MenuFilters
from app.domain.results import ToolResult
from app.memory.recommend import rank
from app.memory.schema import ALLERGEN_MENU_TAG
from app.memory.service import MemoryService
from app.tools.base import Tool, ToolContext


class RecommendItemsArgs(BaseModel):
    """Arguments of recommend_items. None: the customer comes from the session."""


class RecommendItems(Tool[RecommendItemsArgs]):
    """Suggest dishes this customer can eat."""

    name = "recommend_items"
    description = (
        "Use when the customer asks for suggestions or what to order. Returns up to 3 available "
        "dishes that fit their saved diet and allergies, ones they ordered before first. Offer "
        "only these dishes and say why each fits."
    )
    args_model = RecommendItemsArgs

    def run(self, ctx: ToolContext, args: RecommendItemsArgs) -> ToolResult:
        memory = MemoryService(ctx.backend)
        customer_id = ctx.require_customer()
        prefs = memory.read_preferences(customer_id)  # fresh: an allergy stated this turn counts
        menu = ctx.backend.get_menu(
            MenuFilters(
                tags_all=list(prefs.dietary),
                exclude_tags=[
                    ALLERGEN_MENU_TAG[a] for a in prefs.allergies if a in ALLERGEN_MENU_TAG
                ],
            )
        )
        picks = rank(menu, memory.order_history(customer_id))
        data: dict[str, object] = {
            "suggestions": [
                {
                    "id": i.id,
                    "name": i.name,
                    "price": i.price,
                    "category": i.category,
                    "reason": why,
                }
                for i, why in picks
            ]
        }
        if not picks:
            data["note"] = "No available dish fits the customer's saved preferences."
        unchecked = [a for a in prefs.allergies if a not in ALLERGEN_MENU_TAG]
        if unchecked:
            data["unchecked_allergies"] = unchecked  # the menu has no data: tell the customer
        return ToolResult.success(data)

    def compact(self, result: ToolResult, args: RecommendItemsArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        picks = result.data["suggestions"]
        if not picks:
            return "no suggestions"
        return "suggested: " + ", ".join(f"#{p['id']} {p['name']}" for p in picks)
