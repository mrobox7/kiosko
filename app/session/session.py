"""The UI seam. Stage 1 is stateless: each message is its own conversation."""

from dataclasses import dataclass

from app.agent.events import TraceEvent
from app.agent.loop import AgentLoop
from app.domain.messages import Message
from app.session.prompts import FALLBACK_REPLIES, SYSTEM_PROMPT
from app.tools.base import ToolContext


@dataclass(frozen=True)
class Reply:
    """What the UI shows for one customer message."""

    text: str
    events: list[TraceEvent]
    stop_reason: str


class Session:
    """Runs the agent loop on one message and returns the reply."""

    def __init__(self, loop: AgentLoop, ctx: ToolContext) -> None:
        self._loop = loop
        self._ctx = ctx

    def send(self, text: str) -> Reply:
        """Answer one customer message."""
        events: list[TraceEvent] = []
        result = self._loop.run(
            SYSTEM_PROMPT, [Message(role="user", text=text)], self._ctx, events.append
        )
        answered = result.stop_reason == "answered" and result.text.strip()
        reply = result.text.strip() if answered else FALLBACK_REPLIES[result.stop_reason]
        return Reply(text=reply, events=events, stop_reason=result.stop_reason)
