"""check_availability: free tables for a slot."""

from pydantic import BaseModel, Field

from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.common import LocalDatetime, Location


class CheckAvailabilityArgs(BaseModel):
    """Arguments of check_availability."""

    slot_datetime: LocalDatetime = Field(description="Local date and time, ISO 8601, no offset")
    party_size: int = Field(ge=1, description="Number of guests")
    location: Location | None = Field(default=None, description="Seating preference, if any")


class CheckAvailability(Tool[CheckAvailabilityArgs]):
    """Find free tables."""

    name = "check_availability"
    description = (
        "Use before booking to find free tables for a date, time and party size. "
        "Table ids from this tool are required to create a reservation."
    )
    args_model = CheckAvailabilityArgs

    def run(self, ctx: ToolContext, args: CheckAvailabilityArgs) -> ToolResult:
        result = ctx.backend.get_availability(args.slot_datetime, args.party_size, args.location)
        tables = [
            t.model_dump(include={"table_id", "capacity", "location"})
            for t in result.available_tables
        ]
        return ToolResult.success(
            {"slot_datetime": args.slot_datetime.isoformat(), "tables": tables}
        )

    def compact(self, result: ToolResult, args: CheckAvailabilityArgs) -> str:
        if not result.ok:
            return super().compact(result, args)
        slot = result.data["slot_datetime"][:16].replace("T", " ")
        tables = [
            f"table {t['table_id']} (seats {t['capacity']}, {t['location']})"
            for t in result.data["tables"]
        ]
        return f"free {slot}: " + ", ".join(tables) if tables else f"no tables free {slot}"
