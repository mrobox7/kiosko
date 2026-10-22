"""The summary: one short entry per answered turn, built by code from the turn's messages."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.messages import Message

ASKED_MAX = 300  # long enough that a customer's whole sentence, allergy and all, survives
SAID_MAX = 150
SUMMARY_MAX_CHARS = 2000  # about 450 tokens: the whole block never grows past this


def _flat(text: str) -> str:
    return " ".join(text.split())


def _cut_start(text: str, limit: int) -> str:
    """The first `limit` characters: for the customer's words, which say what they want first."""
    flat = _flat(text)
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _cut_end(text: str, limit: int) -> str:
    """The last `limit` characters: for the agent's reply, which ends with its question."""
    flat = _flat(text)
    return flat if len(flat) <= limit else "…" + flat[-(limit - 1) :]


@dataclass(frozen=True)
class TurnSummary:
    """What the customer asked, what each tool call came to, what the agent said. Calls whose
    result the order in the context already shows are left out; `used_tools` still says the
    turn had tool calls, so its messages are never sent whole."""

    number: int
    asked: str
    calls: list[str]
    said: str
    used_tools: bool = False

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
    """Pair each tool call with its outcome's compact line, except calls the order shows."""
    names: dict[str, str] = {}
    calls: list[str] = []
    for message in new_messages:
        for call in message.tool_calls:
            names[call.id] = call.name
        for outcome in message.tool_outcomes:
            if not outcome.in_order:
                calls.append(f"{names.get(outcome.call_id, 'tool')} -> {outcome.compact}")
    used_tools = any(m.tool_calls for m in new_messages)
    return TurnSummary(
        number, _cut_start(user_text, ASKED_MAX), calls, _cut_end(reply, SAID_MAX), used_tools
    )


def render_summary(entries: Sequence[TurnSummary], limit: int = SUMMARY_MAX_CHARS) -> str:
    """The prompt block, oldest first. Empty when there is nothing to show. Over `limit`, the
    oldest entries give way to a count; the newest always stays."""
    if not entries:
        return ""
    header = "Earlier turns (short form, oldest first; call a tool for fresh data):"
    lines = [e.render() for e in entries]

    def block(hidden: int) -> str:
        note = [f"({hidden} earlier turns not shown)"] if hidden else []
        return "\n".join([header, *note, *lines[hidden:]])

    hidden = 0
    while len(block(hidden)) > limit and hidden < len(lines) - 1:
        hidden += 1
    return block(hidden)
