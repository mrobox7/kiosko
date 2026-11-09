"""The first node, plain code: refuses a message the model should never see, starts a chat, and
clears what only lived for the last turn."""

from datetime import timedelta

from langgraph.types import Overwrite

from app.agent.services import Services
from app.agent.state import State
from app.agent.trace import GuardDecided

STARTED = "started"


def _refusal(services: Services, state: State, text: str) -> tuple[str, str] | None:
    """The reason and the canned reply for a message that must be refused, else None."""
    if not text.strip():
        return "empty", "Please type a message and I will help."
    if len(text) > services.max_chars:
        return (
            "too_long",
            f"Message too long. Please keep it under {services.max_chars} characters.",
        )
    if state.get("tokens_used", 0) >= services.token_budget:
        return "token_budget", "This chat has reached its limit. Please start a new chat."
    return None


def guard(state: State, services: Services) -> dict[str, object]:
    """Start the chat, or check the customer's message against the rules."""
    if state.get("kind") == "start":
        return {
            "status": "open",
            "outlet": services.outlet,
            "reply": "",
            "stop_reason": STARTED,
            "events": Overwrite([]),
        }
    now = services.clock()
    recent = [t for t in state.get("recent_turns", []) if now - t < timedelta(minutes=1)]
    refusal = _refusal(services, state, state.get("user_text", ""))
    if refusal is None and len(recent) >= services.turns_per_min:
        refusal = ("rate_limit", "You are sending messages too quickly. Please wait a moment.")
    fresh: dict[str, object] = {"reply": "", "stop_reason": "", "events": Overwrite([])}
    if refusal is not None:
        reason, reply = refusal
        event = GuardDecided(action="refuse", reason=reason)
        return {
            **fresh,
            "reply": reply,
            "stop_reason": reason,
            "recent_turns": recent,
            "events": Overwrite([event]),
        }
    event = GuardDecided(action="pass", reason="")
    return {**fresh, "recent_turns": [*recent, now], "events": Overwrite([event])}


def after_guard(state: State) -> str:
    """Go on to `supervisor` only when the message passed."""
    return "supervisor" if not state.get("stop_reason") else "end"
