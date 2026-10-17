"""list_my_reservations: the customer's own bookings."""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.common import reservation_view


class ListMyReservationsArgs(BaseModel):
    """Arguments of list_my_reservations."""

    status: Literal["confirmed", "cancelled", "completed"] | None = Field(
        default=None, description="Only reservations with this status"
    )


class ListMyReservations(Tool[ListMyReservationsArgs]):
    """List the bound customer's reservations."""

    name = "list_my_reservations"
    description = (
        "Use when the customer asks about their bookings, or you need a reservation id "
        "and none is known from the conversation."
    )
    args_model = ListMyReservationsArgs

    def run(self, ctx: ToolContext, args: ListMyReservationsArgs) -> ToolResult:
        items = ctx.backend.list_customer_reservations(ctx.require_customer(), args.status)
        return ToolResult.success({"reservations": [reservation_view(r) for r in items]})

    def compact(self, result: ToolResult, args: ListMyReservationsArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        bookings = [
            f"#{r['id']} {r['slot_datetime'][:16].replace('T', ' ')} party {r['party_size']}"
            f" table {r['table_id']} {r['status']}"
            for r in result.data["reservations"]
        ]
        return "; ".join(bookings) or "no reservations"
