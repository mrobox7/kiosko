"""Owner of chat state: customer, history, working state, write ledger, usage."""

from collections.abc import Callable
from dataclasses import dataclass

from app.agent.events import GuardDecided, LLMCalled, TraceEvent
from app.agent.loop import AgentLoop
from app.backend.errors import BackendError
from app.backend.models import Customer, Reservation
from app.domain.messages import Message
from app.domain.state import Clock, LedgerEntry, WorkingState, next_state
from app.guards.base import Guard
from app.memory.service import MemoryService
from app.session.context_builder import build_context
from app.session.prompts import FALLBACK_REPLIES, system_prompt
from app.session.summary import TurnSummary, render_summary, split_turns, summarise_turn
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
        self,
        *,
        customer: Customer,
        loop: AgentLoop,
        ctx: ToolContext,
        guard: Guard,
        clock: Clock,
        memory: MemoryService,
        summary_turns: int,
    ) -> None:
        self.customer = customer
        self.history: list[Message] = []
        self.state = WorkingState()
        self.ledger: list[LedgerEntry] = []
        self.tokens_used = 0
        self._memory = memory
        self.profile = memory.load_profile(customer.id, customer.name)
        self._loop = loop
        self._ctx = ctx
        self._guard = guard
        self._clock = clock
        self._summary_turns = summary_turns
        self.summary: list[TurnSummary] = []
        self.upcoming = self._load_upcoming()

    def send(
        self, text: str, *, spoken: bool = False, on_text: Callable[[str], None] | None = None
    ) -> Reply:
        """Answer one customer message. `spoken` marks dictated text that will be read aloud.
        With `on_text`, reply text is passed on as it is written, before the turn ends."""
        events: list[TraceEvent] = []
        now = self._clock()
        decision = self._guard.check(text, now=now, tokens_used=self.tokens_used)
        events.append(GuardDecided(action=decision.action, reason=decision.reason))
        if decision.action == "refuse":
            return Reply(text=decision.reply, events=events, stop_reason="refused")

        user = Message(role="user", text=text)
        earlier, messages = self._context()
        # The context is its own system message right before the customer's text. It is sent
        # to the model but never stored in history.
        context = Message(
            role="system",
            text=build_context(
                self.customer.name, self.state, now, self.profile, self.upcoming, earlier
            ),
        )
        result = self._loop.run(
            system_prompt(spoken), [*messages, context, user], self._ctx, events.append, on_text
        )

        self.tokens_used += sum(
            e.input_tokens + e.output_tokens for e in events if isinstance(e, LLMCalled)
        )
        for entry in result.writes:
            self.ledger.append(entry)
            self.state = next_state(self.state, entry)
        if any(w.action in ("created", "cancelled") for w in result.writes):
            self.upcoming = self._load_upcoming()
        if any(w.action == "preferences_updated" for w in result.writes):
            self.profile = self._memory.load_profile(self.customer.id, self.customer.name)

        if result.stop_reason == "answered" and result.text.strip():
            self.history.extend([user, *result.new_messages])
            self.summary.append(
                summarise_turn(len(self.summary) + 1, text, result.new_messages, result.text)
            )
            return Reply(text=result.text.strip(), events=events, stop_reason="answered")

        # Failed turn: drop it, but never hide writes that already happened.
        reply = FALLBACK_REPLIES[result.stop_reason]
        if result.changes:
            reply = f"{reply} Changes already made: {'; '.join(result.changes)}."
        return Reply(text=reply, events=events, stop_reason=result.stop_reason)

    def _load_upcoming(self) -> list[Reservation] | None:
        """The customer's confirmed bookings from now on, soonest first. None if the backend
        could not say. A plain read: it costs no model call."""
        try:
            booked = self._ctx.backend.list_customer_reservations(self.customer.id, "confirmed")
        except BackendError:
            return None
        now = self._clock().replace(tzinfo=None)
        return sorted((r for r in booked if r.slot_datetime >= now), key=lambda r: r.slot_datetime)

    def _context(self) -> tuple[str, list[Message]]:
        """History as the model sees it: of the last k turns before the latest, those that called
        tools become summary lines and chat-only ones stay word for word (they are cheap, and an
        answer stays next to its question). The latest turn is always word for word."""
        turns = split_turns(self.history)
        if not turns:
            return "", []
        earlier, latest = turns[:-1], turns[-1]
        recent = range(max(0, len(earlier) - self._summary_turns), len(earlier))
        summarised = [self.summary[i] for i in recent if self.summary[i].calls]
        verbatim = [m for i in recent if not self.summary[i].calls for m in earlier[i]]
        return render_summary(summarised), [*verbatim, *latest]
