"""note_need: the customer said what they cannot or will not eat."""

from pydantic import BaseModel, Field, model_validator

from app.backend.errors import BackendError
from app.domain.results import ToolResult
from app.domain.state import Allergen
from app.tools.base import Tool, ToolContext
from app.tools.recover import settle


class NoteNeedArgs(BaseModel):
    """Arguments of note_need."""

    allergies: list[Allergen] = Field(default_factory=list)
    veg_only: bool = False

    @model_validator(mode="after")
    def _something_to_note(self) -> NoteNeedArgs:
        if not self.allergies and not self.veg_only:
            raise ValueError("send at least one allergy, or veg_only")
        return self


class NoteNeed(Tool[NoteNeedArgs]):
    """Remember an allergy or a vegetarian diet for the whole order."""

    name = "note_need"
    description = (
        "Call it the moment the customer says they are allergic to something or eat only "
        "vegetarian, even in passing. It is kept for the whole order and shown to you as `Needs` "
        "on every turn, and saved to their record if they have given a number. `veg_only` is "
        "true for vegetarian. It only adds: it cannot take a need back."
    )
    args_model = NoteNeedArgs
    mutating = True

    def run(self, ctx: ToolContext, args: NoteNeedArgs) -> ToolResult:
        needs = ctx.caller.needs
        needs.add(args.allergies, args.veg_only)
        data: dict[str, object] = {"allergies": needs.allergies, "veg_only": needs.veg_only}
        customer = ctx.caller.customer
        if customer is not None:
            data["saved_to_record"] = self._save(ctx, customer.id)
        return ToolResult(ok=True, data=data)

    @staticmethod
    def _save(ctx: ToolContext, customer_id: int) -> bool:
        """Put the allergies on the customer's record, with the ones already there. Ordering goes
        on if this fails: the need still holds for this chat."""
        everything = ctx.caller.avoid
        try:
            ctx.caller.customer = settle(
                lambda: ctx.backend.patch_preferences(customer_id, {"allergies": everything}),
                landed=lambda: None,
            )
        except BackendError:
            return False
        return True

    def compact(self, result: ToolResult, args: NoteNeedArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        noted = [*args.allergies, *(["veg only"] if args.veg_only else [])]
        return f"noted: {', '.join(noted)}"
