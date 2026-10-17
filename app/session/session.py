"""Owner of chat state: customer, history, working state, write ledger, usage."""

from dataclasses import dataclass

from app.agent.events import GuardDecided, LLMCalled, TraceEvent
from app.agent.loop import AgentLoop
from app.backend.models import Customer
from app.domain.messages import Message
from app.domain.state import Clock, LedgerEntry, WorkingState, next_state
from app.guards.base import Guard
from app.session.context_builder import build_system_prompt
from app.session.prompts import FALLBACK_REPLIES
from app.tools.base import ToolContext


@dataclass(frozen=True)
class Reply:
    """What the UI shows for one customer message."""

    text: str
    events: list[TraceEvent]
    stop_reason: str


class Session:
    """One chat. A turn is committed to history only if it ended normally."""

    def __init__(
        self, *, customer: Customer, loop: AgentLoop, ctx: ToolContext, guard: Guard, clock: Clock
    ) -> None:
        self.customer = customer
        self.history: list[Message] = []
        self.state = WorkingState()
        self.ledger: list[LedgerEntry] = []
        self.tokens_used = 0
        self._loop = loop
        self._ctx = ctx
        self._guard = guard
        self._clock = clock

    def send(self, text: str) -> Reply:
        """Answer one customer message."""
        events: list[TraceEvent] = []
        now = self._clock()
        decision = self._guard.check(text, now=now, tokens_used=self.tokens_used)
        events.append(GuardDecided(action=decision.action, reason=decision.reason))
        if decision.action == "refuse":
            return Reply(text=decision.reply, events=events, stop_reason="refused")

        user = Message(role="user", text=text)
        system = build_system_prompt(self.customer.name, self.state, now)
        result = self._loop.run(system, [*self.history, user], self._ctx, events.append)

        self.tokens_used += sum(
            e.input_tokens + e.output_tokens for e in events if isinstance(e, LLMCalled)
        )
        for entry in result.writes:
            self.ledger.append(entry)
            self.state = next_state(self.state, entry)

        if result.stop_reason == "answered" and result.text.strip():
            self.history.extend([user, *result.new_messages])
            return Reply(text=result.text.strip(), events=events, stop_reason="answered")

        # Failed turn: drop it, but never hide writes that already happened.
        reply = FALLBACK_REPLIES[result.stop_reason]
        if result.writes:
            changes = "; ".join(w.summary for w in result.writes)
            reply = f"{reply} Changes already made: {changes}."
        return Reply(text=reply, events=events, stop_reason=result.stop_reason)
