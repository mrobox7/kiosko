"""The last node, plain code: remembers the turn. It keeps the words of the latest turns, keeps
only the questions still open, and marks the chat placed once the order is confirmed. The session
also writes the state as this node when a tap on the screen changes the order."""

from app.agent.items import OPEN
from app.agent.state import State, Turn
from app.agent.trace import TurnEnded

HISTORY = 3  # turns kept, word for word
ANSWERED = "answered"  # the stop_reason of a turn that ran to its reply


def commit(state: State) -> dict[str, object]:
    turn = Turn(user=state.get("user_text", ""), reply=state.get("reply", ""))
    reason = state.get("stop_reason") or ANSWERED
    changes: dict[str, object] = {
        "stop_reason": reason,
        "items": [i for i in state.get("items", []) if i.status in OPEN],
        "history": [*state.get("history", []), turn][-HISTORY:],
        "turns_done": state.get("turns_done", 0) + 1,
        "events": [TurnEnded(reason)],
    }
    order = state.get("order")
    if order is not None and order.status == "confirmed":
        changes["status"] = "placed"
    return changes
