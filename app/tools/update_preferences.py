"""update_preferences: save something the customer stated as lasting."""

from pydantic import BaseModel, Field

from app.domain.results import INVALID_ARGUMENTS, ToolResult
from app.memory.schema import Allergen, Dietary, Seating
from app.memory.service import MemoryService
from app.tools.base import Tool, ToolContext


class UpdatePreferencesArgs(BaseModel):
    """Arguments of update_preferences. Everything is an explicit add or remove."""

    seating: Seating | None = Field(default=None, description="Lasting seating preference")
    dietary_add: list[Dietary] = Field(default_factory=list)
    dietary_remove: list[Dietary] = Field(default_factory=list)
    allergies_add: list[Allergen] = Field(default_factory=list)
    allergies_remove: list[Allergen] = Field(default_factory=list)


class UpdatePreferences(Tool[UpdatePreferencesArgs]):
    """Save a stated preference or allergy to the customer's profile."""

    name = "update_preferences"
    description = (
        "Use only when the customer states something as lasting ('I always prefer indoor', "
        "'I am allergic to nuts'). Never for one-off requests or guesses. Existing values "
        "are kept; list only what to add or remove."
    )
    args_model = UpdatePreferencesArgs
    mutating = True

    def run(self, ctx: ToolContext, args: UpdatePreferencesArgs) -> ToolResult:
        customer_id = ctx.require_customer()
        if not (args.seating or args.dietary_add or args.dietary_remove
                or args.allergies_add or args.allergies_remove):  # fmt: skip
            return ToolResult.failure(
                INVALID_ARGUMENTS,
                "Nothing to save.",
                "Give at least one preference to add or remove.",
            )
        prefs, changed = MemoryService(ctx.backend).update_preferences(
            customer_id, **args.model_dump()
        )
        remembered = prefs.model_dump(exclude_defaults=False)
        if not changed:
            return ToolResult.success({"saved": False, "note": "Already remembered.", **remembered})
        entry = ctx.ledger(self.name, "preferences_updated", customer_id)
        return ToolResult(ok=True, data={"saved": True, **remembered}, writes=[entry])

    def compact(self, result: ToolResult, args: UpdatePreferencesArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        if not result.data["saved"]:
            return "preferences unchanged (already remembered)"
        now = [f"seating {result.data['seating']}"] if result.data["seating"] else []
        now += [
            f"{label} {', '.join(result.data[key])}"
            for key, label in (("dietary", "dietary"), ("allergies", "allergies"))
            if result.data[key]
        ]
        return "preferences saved, now: " + "; ".join(now)
