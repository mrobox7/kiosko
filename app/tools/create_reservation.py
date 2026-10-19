"""create_reservation: book a table."""

from pydantic import BaseModel, Field

from app.backend.errors import BackendConflict
from app.domain.results import BACKEND_REJECTED, ToolResult
from app.domain.state import WorkingState
from app.tools.base import Tool, ToolContext
from app.tools.common import LocalDatetime, Location, reservation_view


class CreateReservationArgs(BaseModel):
    """Arguments of create_reservation."""

    slot_datetime: LocalDatetime = Field(description="Local date and time, ISO 8601, no offset")
    party_size: int = Field(ge=1, description="Number of guests")
    location: Location | None = Field(default=None, description="Seating wanted, if any")


class CreateReservation(Tool[CreateReservationArgs]):
    """Book a table for the bound customer."""

    name = "create_reservation"
    description = (
        "Use to book a table for the current customer once you have the date, time and party "
        "size. Picks the smallest free table that fits. If the wanted seating is full it books "
        "nothing and says what is free."
    )
    args_model = CreateReservationArgs
    mutating = True

    def run(self, ctx: ToolContext, args: CreateReservationArgs) -> ToolResult:
        customer_id = ctx.require_customer()
        free = ctx.backend.get_availability(args.slot_datetime, args.party_size, args.location)
        # Smallest table that fits first, so big tables stay free for big parties.
        for table in sorted(free.available_tables, key=lambda t: (t.capacity, t.table_id)):
            try:
                r = ctx.backend.create_reservation(
                    customer_id, table.table_id, args.slot_datetime, args.party_size
                )
            except BackendConflict:
                continue  # taken since we looked: try the next table
            state = WorkingState(
                reservation_id=r.id,
                slot_datetime=r.slot_datetime,
                party_size=r.party_size,
                table_id=r.table_id,
            )
            entry = ctx.ledger(self.name, "created", r.id, state)
            return ToolResult(
                ok=True, data={**reservation_view(r), "location": table.location}, writes=[entry]
            )
        return self._no_table(ctx, args)

    @staticmethod
    def _no_table(ctx: ToolContext, args: CreateReservationArgs) -> ToolResult:
        """Nothing was booked. Say what else is free, so the customer chooses."""
        slot = f"{args.slot_datetime:%Y-%m-%d %H:%M}"
        if args.location:
            elsewhere = ctx.backend.get_availability(args.slot_datetime, args.party_size)
            seatings = sorted({t.location for t in elsewhere.available_tables} - {args.location})
            if seatings:
                return ToolResult.failure(
                    BACKEND_REJECTED,
                    f"No {args.location} table for {args.party_size} is free at {slot}. "
                    f"Free: {', '.join(seatings)}.",
                    "Nothing was booked. Ask the customer whether to book the other seating "
                    "or choose another time.",
                )
        return ToolResult.failure(
            BACKEND_REJECTED,
            f"No table for {args.party_size} is free at {slot}.",
            "Nothing was booked. Offer another time.",
        )

    def compact(self, result: ToolResult, args: CreateReservationArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        r = result.data
        slot = r["slot_datetime"][:16].replace("T", " ")
        return f"Reservation #{r['id']} for {r['party_size']} at {slot} (table {r['table_id']})"
