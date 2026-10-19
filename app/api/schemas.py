"""Request and response bodies of the HTTP API."""

import dataclasses
from typing import Any

from pydantic import BaseModel, Field

from app.agent.events import TraceEvent
from app.session.session import Session


class LoginIn(BaseModel):
    """Who is chatting. A phone number or an email is needed; a name only for new customers."""

    name: str = ""
    phone: str = ""
    email: str = ""


class MessageIn(BaseModel):
    """One customer message."""

    text: str = Field(min_length=1)


class CustomerOut(BaseModel):
    """The identified customer."""

    id: int
    name: str


class FactOut(BaseModel):
    """One remembered fact, for the sidebar."""

    label: str
    value: str


class BookingOut(BaseModel):
    """One upcoming booking."""

    id: int
    slot_datetime: str
    party_size: int
    table_id: int


class SessionOut(BaseModel):
    """What the page shows around the chat. `greeting` is set only when a chat starts."""

    session_id: str
    customer: CustomerOut
    greeting: str | None = None
    remembered: list[FactOut]
    memory_unavailable: bool
    upcoming: list[BookingOut] | None  # None: the bookings could not be loaded
    voice: bool  # True when the page can offer the microphone


class ReplyOut(BaseModel):
    """The answer to one message, with the trace the page can show."""

    text: str
    stop_reason: str
    trace: list[dict[str, Any]]


def trace_of(events: list[TraceEvent]) -> list[dict[str, Any]]:
    """The trace as plain dicts, each tagged with its event name."""
    return [{"event": type(e).__name__, **dataclasses.asdict(e)} for e in events]


def session_out(
    session_id: str, session: Session, *, voice: bool, greeting: str | None = None
) -> SessionOut:
    """Describe a chat's session for the page."""
    upcoming = (
        None
        if session.upcoming is None
        else [
            BookingOut(
                id=r.id,
                slot_datetime=r.slot_datetime.isoformat(),
                party_size=r.party_size,
                table_id=r.table_id,
            )
            for r in session.upcoming
        ]
    )
    return SessionOut(
        session_id=session_id,
        customer=CustomerOut(id=session.customer.id, name=session.customer.name),
        greeting=greeting,
        remembered=[FactOut(label=k, value=v) for k, v in session.profile.facts()],
        memory_unavailable=session.profile.memory_unavailable,
        upcoming=upcoming,
        voice=voice,
    )
