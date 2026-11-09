"""The graph state. `items` is what carries a half-finished request from one turn to the next;
the order and the customer's needs are what the tools read and change."""

import operator
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel

from app.agent.items import Item
from app.agent.trace import TraceEvent
from app.backend.models import Customer, Order, Outlet

Status = Literal["open", "placed", "abandoned"]
Kind = Literal["start", "message"]


class Turn(BaseModel):
    """One finished turn, word for word."""

    user: str
    reply: str


def union(left: list[str], right: list[str]) -> list[str]:
    return [*left, *(a for a in right if a not in left)]


class State(TypedDict, total=False):
    # --- saved with the chat
    status: Status
    items: list[Item]  # only open questions are kept between turns
    history: list[Turn]  # the last few turns
    turns_done: int
    order: Order | None
    customer: Customer | None
    usual: list[str]
    allergies: Annotated[list[str], union]
    veg_only: bool
    outlet: Outlet
    tokens_used: Annotated[int, operator.add]
    recent_turns: list[datetime]  # for the rate limit
    # --- this turn only: reset when the next turn starts
    kind: Kind
    user_text: str
    spoken: bool
    language: str
    reply: str
    stop_reason: str  # why the turn ended early; empty for a full turn
    events: Annotated[list[TraceEvent], operator.add]


class Input(TypedDict, total=False):
    """What a run is started with."""

    kind: Kind
    user_text: str
    spoken: bool


class Output(TypedDict, total=False):
    """What a run hands back to the session."""

    reply: str
    stop_reason: str
    events: list[TraceEvent]
    order: Order | None
    status: Status
    items: list[Item]
    language: str


class RunContext(TypedDict, total=False):
    on_text: Callable[[str], None]  # gets the reply as it is written
