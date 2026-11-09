"""note_need: the customer said what they cannot or will not eat."""

from pydantic import BaseModel, Field, model_validator

from app.backend.errors import BackendError
from app.backend.models import Allergen, Customer, allergies_on_file
from app.tools.backend_errors import settle
from app.tools.contract import Tool, ToolContext, ToolResult, Update


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
    args_model = NoteNeedArgs

    def run(self, ctx: ToolContext, args: NoteNeedArgs) -> ToolResult:
        allergies = [*ctx.allergies, *(a for a in args.allergies if a not in ctx.allergies)]
        veg_only = ctx.veg_only or args.veg_only
        data: dict[str, object] = {"allergies": allergies, "veg_only": veg_only}
        update = Update(allergies=list(args.allergies), veg_only=args.veg_only)
        customer = ctx.customer
        if customer is not None:
            saved = self._save(ctx, customer, allergies)
            data["saved_to_record"] = saved is not None
            update.customer = saved
        return ToolResult(ok=True, data=data, update=update)

    @staticmethod
    def _save(ctx: ToolContext, customer: Customer, said: list[str]) -> Customer | None:
        """Put the allergies on the customer's record, with the ones already there; the updated
        record, or None when that failed. Ordering goes on if it fails: the need still holds for
        this chat."""
        on_file = allergies_on_file(customer)
        everything = [*on_file, *(a for a in said if a not in on_file)]
        try:
            return settle(
                lambda: ctx.backend.patch_preferences(customer.id, {"allergies": everything}),
                landed=lambda: None,
            )
        except BackendError:
            return None
