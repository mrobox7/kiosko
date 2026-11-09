"""Request and response bodies of the HTTP API."""

import dataclasses
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.trace import TraceEvent
from app.backend.models import Category, Dish, Outlet
from app.session.session import Session


class MessageIn(BaseModel):
    """One customer message."""

    text: str = Field(min_length=1)


class CustomerOut(BaseModel):
    """The customer, once they have given a phone number."""

    id: int
    name: str | None


class LineOut(BaseModel):
    """One line of the order."""

    id: int
    dish_id: int | None
    name: str
    quantity: int
    meal_size: str | None
    options: list[str]
    note: str | None
    line_total: float


class OrderOut(BaseModel):
    """The order so far; once placed it has its number. Prices are in rupees, GST on the total."""

    id: int
    status: str
    order_number: int | None
    lines: list[LineOut]
    subtotal: float
    gst: float
    total: float


class SessionOut(BaseModel):
    """What the page shows around the chat. `greeting` is set only when a chat starts."""

    session_id: str
    status: str  # open | placed | abandoned
    customer: CustomerOut | None
    order: OrderOut | None
    greeting: str | None = None
    voice: bool  # True when the page can offer the microphone
    idle_timeout_s: float  # seconds without a message after which the server ends the chat


class ReplyOut(BaseModel):
    """The answer to one message, with the trace the page can show."""

    text: str
    stop_reason: str
    trace: list[dict[str, Any]]


def trace_of(events: list[TraceEvent]) -> list[dict[str, Any]]:
    """The trace as plain dicts, each tagged with its event name."""
    return [{"event": type(e).__name__, **dataclasses.asdict(e)} for e in events]


def session_out(
    session_id: str,
    session: Session,
    *,
    voice: bool,
    idle_timeout_s: float,
    greeting: str | None = None,
) -> SessionOut:
    """Describe a chat's session for the page."""
    customer, latest = session.customer, session.order
    return SessionOut(
        session_id=session_id,
        status=session.status,
        customer=CustomerOut(id=customer.id, name=customer.name) if customer else None,
        order=None
        if latest is None
        else OrderOut(
            id=latest.id,
            status=latest.status,
            order_number=latest.order_number,
            lines=[
                LineOut(
                    id=i.id,
                    dish_id=i.product_id,
                    name=i.name,
                    quantity=i.quantity,
                    meal_size=i.meal_size,
                    options=[
                        o["name"] if o["qty"] == 1 else f"{o['qty']}x {o['name']}"
                        for o in i.options
                    ],
                    note=i.note,
                    line_total=i.line_total,
                )
                for i in latest.lines
            ],
            subtotal=latest.subtotal,
            gst=latest.gst,
            total=latest.total,
        ),
        greeting=greeting,
        voice=voice,
        idle_timeout_s=idle_timeout_s,
    )


class OptionIn(BaseModel):
    """A choice picked on the screen, by its id; `qty` above 1 means it is picked more than once."""

    option_id: int
    qty: int = Field(default=1, ge=1, le=10)


class LineIn(BaseModel):
    """A dish added from the screen, with the choices made on its sheet."""

    dish_id: int
    quantity: int = Field(default=1, ge=1, le=20)
    meal_size: Literal["Medium", "Large"] | None = None
    options: list[OptionIn] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=200)


class QuantityIn(BaseModel):
    """The new count of a line already on the order."""

    quantity: int = Field(ge=1, le=20)


class MenuOut(BaseModel):
    """The menu to browse: sections, then dishes with their choices, meals, pictures and facts."""

    version: str
    outlet: Outlet
    categories: list[Category]
    dishes: list[Dish]
