"""Builds the per-turn context message. Holds no state.

The system message is fixed text and is never mixed with anything that changes: the time, the
reservation, the profile and the summary all live in this separate message, which the Session
puts right before the customer's own message."""

from collections.abc import Sequence
from datetime import datetime

from app.backend.models import Reservation
from app.domain.state import WorkingState
from app.memory.profile import CustomerProfile

HEADING = "Context for this turn"
SHOWN_BOOKINGS = 3


def _upcoming_block(upcoming: Sequence[Reservation] | None) -> list[str]:
    """The customer's next bookings. Left out when they could not be loaded, so the model is
    never told "none" on a guess."""
    if upcoming is None:
        return []
    if not upcoming:
        return ["Upcoming bookings: none"]
    lines = [
        f"- #{r.id} {r.slot_datetime:%a %Y-%m-%d %H:%M}, party of {r.party_size}, "
        f"table {r.table_id}"
        for r in upcoming[:SHOWN_BOOKINGS]
    ]
    more = len(upcoming) - SHOWN_BOOKINGS
    return ["Upcoming bookings:", *lines, *([f"- and {more} more"] if more > 0 else [])]


def _working_state_block(state: WorkingState) -> list[str]:
    if state.reservation_id is None:
        return []
    slot = f"{state.slot_datetime:%Y-%m-%d %H:%M}" if state.slot_datetime else "unknown time"
    return [
        f"Active reservation: #{state.reservation_id}, {slot}, "
        f"party of {state.party_size}, table {state.table_id}"
    ]


def build_context(
    customer_name: str,
    state: WorkingState,
    now: datetime,
    profile: CustomerProfile,
    upcoming: Sequence[Reservation] | None = None,
    earlier: str = "",
) -> str:
    """Everything the model needs that is not the customer's words and changes between turns."""
    return "\n".join(
        [
            f"{HEADING}:",
            f"Current date and time: {now:%A %Y-%m-%d %H:%M} ({now.tzname()})",
            f"Customer: {customer_name}",
            *_upcoming_block(upcoming),
            *_working_state_block(state),
            profile.render(),
            *([earlier] if earlier else []),
        ]
    )
