"""cancel_reservation: cancel one of the customer's bookings."""

from pydantic import BaseModel

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.checks import own_reservation
from app.tools.common import reservation_view


class CancelReservationArgs(BaseModel):
    """Arguments of cancel_reservation."""

    reservation_id: int


class CancelReservation(Tool[CancelReservationArgs]):
    """Cancel a reservation."""

    name = "cancel_reservation"
    description = (
        "Use to cancel a reservation, only after the customer has explicitly confirmed "
        "which booking to cancel. The restaurant may refuse late cancellations."
    )
    args_model = CancelReservationArgs
    mutating = True
    destructive = True

    def run(self, ctx: ToolContext, args: CancelReservationArgs) -> ToolResult:
        own_reservation(ctx, args.reservation_id)
        r = ctx.backend.cancel_reservation(args.reservation_id)
        entry = ctx.ledger(self.name, "cancelled", r.id)
        return ToolResult(ok=True, data=reservation_view(r), writes=[entry])

    def compact(self, result: ToolResult, args: CancelReservationArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        return f"Reservation #{result.data['id']} cancelled"
