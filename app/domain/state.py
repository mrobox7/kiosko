"""Session-held state: the working reservation and the write ledger."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Clock = Callable[[], datetime]


class WorkingState(BaseModel):
    """The reservation the conversation is about. Updated only from successful writes."""

    reservation_id: int | None = None
    slot_datetime: datetime | None = None
    party_size: int | None = None
    table_id: int | None = None


LedgerAction = Literal["created", "cancelled", "added", "removed"]


class LedgerEntry(BaseModel):
    """One successful backend write. `state` is set when it establishes a working reservation."""

    tool: str
    action: LedgerAction
    entity_id: int
    summary: str
    timestamp: datetime
    state: WorkingState | None = None


def next_state(state: WorkingState, entry: LedgerEntry) -> WorkingState:
    """Apply one write to the working state."""
    if entry.action == "created" and entry.state is not None:
        return entry.state
    if entry.action == "cancelled" and entry.entity_id == state.reservation_id:
        return WorkingState()
    return state
