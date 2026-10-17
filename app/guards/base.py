"""Input guard interface."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel


class GuardDecision(BaseModel):
    """Verdict on a customer message. `reply` is the canned text when refusing."""

    action: Literal["pass", "refuse", "flag"]
    reason: str = ""
    reply: str = ""


class Guard(Protocol):
    """Decides whether a message reaches the model."""

    def check(self, text: str, *, now: datetime, tokens_used: int) -> GuardDecision:
        """Judge one message. A passing message counts as a turn."""
        ...
