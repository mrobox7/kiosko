"""create_reservation: book a table."""

from pydantic import BaseModel, Field

from app.domain.results import ToolResult
from app.domain.state import WorkingState
from app.tools.base import Tool, ToolContext
from app.tools.common import LocalDatetime, reservation_view


class CreateReservationArgs(BaseModel):
    """Arguments of create_reservation."""

    table_id: int = Field(description="Table id from check_availability")
    slot_datetime: LocalDatetime = Field(description="Local date and time, ISO 8601, no offset")
    party_size: int = Field(ge=1, description="Number of guests")


class CreateReservation(Tool[CreateReservationArgs]):
    """Book a table for the bound customer."""

    name = "create_reservation"
    description = (
        "Use to book a table once the customer has confirmed date, time and party size "
        "and you have checked availability. The booking is for the current customer."
    )
    args_model = CreateReservationArgs
    mutating = True

    def run(self, ctx: ToolContext, args: CreateReservationArgs) -> ToolResult:
        r = ctx.backend.create_reservation(
            ctx.require_customer(), args.table_id, args.slot_datetime, args.party_size
        )
        state = WorkingState(
            reservation_id=r.id,
            slot_datetime=r.slot_datetime,
            party_size=r.party_size,
            table_id=r.table_id,
        )
        entry = ctx.ledger(self.name, "created", r.id, state)
        return ToolResult(ok=True, data=reservation_view(r), writes=[entry])

    def compact(self, result: ToolResult, args: CreateReservationArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        r = result.data
        slot = r["slot_datetime"][:16].replace("T", " ")
        return f"Reservation #{r['id']} for {r['party_size']} at {slot} (table {r['table_id']})"
