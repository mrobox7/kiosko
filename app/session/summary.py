"""The summary: one short entry per answered turn, built by code from the turn's messages."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.messages import Message

ASKED_MAX = 100
SAID_MAX = 150


def _cut(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


@dataclass(frozen=True)
class TurnSummary:
    """What the customer asked, what each tool call came to, what the agent said."""

    number: int
    asked: str
    calls: list[str]
    said: str

    def render(self) -> str:
        parts = [f'T{self.number} asked: "{self.asked}"', *self.calls, f'said: "{self.said}"']
        return " | ".join(parts)


def split_turns(history: Sequence[Message]) -> list[list[Message]]:
    """Group the flat history into turns; each starts at a customer text message."""
    turns: list[list[Message]] = []
    for message in history:
        if message.role == "user" and message.text is not None:
            turns.append([])
        if turns:
            turns[-1].append(message)
    return turns


def summarise_turn(
    number: int, user_text: str, new_messages: Sequence[Message], reply: str
) -> TurnSummary:
    """Pair each tool call with its outcome's compact line."""
    names: dict[str, str] = {}
    calls: list[str] = []
    for message in new_messages:
        for call in message.tool_calls:
            names[call.id] = call.name
        for outcome in message.tool_outcomes:
            calls.append(f"{names.get(outcome.call_id, 'tool')} -> {outcome.compact}")
    return TurnSummary(number, _cut(user_text, ASKED_MAX), calls, _cut(reply, SAID_MAX))


def render_summary(entries: Sequence[TurnSummary]) -> str:
    """The prompt block, oldest first. Empty when there is nothing to show."""
    if not entries:
        return ""
    header = "Earlier turns (short form, oldest first; call a tool for fresh data):"
    return "\n".join([header, *(e.render() for e in entries)])
