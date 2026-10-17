"""Assembles the system prompt for a turn. Holds no state."""

from datetime import datetime

from app.domain.state import WorkingState
from app.session.prompts import STABLE_PROMPT


def _working_state_block(state: WorkingState) -> str:
    if state.reservation_id is None:
        return "Active reservation: none"
    slot = f"{state.slot_datetime:%Y-%m-%d %H:%M}" if state.slot_datetime else "unknown time"
    return (
        f"Active reservation: #{state.reservation_id}, {slot}, "
        f"party of {state.party_size}, table {state.table_id}"
    )


def build_system_prompt(customer_name: str, state: WorkingState, now: datetime) -> str:
    """Stable instructions first; the volatile block (time, customer, state) goes last."""
    volatile = "\n".join(
        [
            f"Current date and time: {now:%A %Y-%m-%d %H:%M} ({now.tzname()})",
            f"Customer: {customer_name}",
            _working_state_block(state),
        ]
    )
    return f"{STABLE_PROMPT}\n\n{volatile}"
