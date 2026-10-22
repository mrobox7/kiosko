"""Owner of chat state: the order, who is ordering, history, usage. One session is one order."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.agent.events import GuardDecided, LLMCalled, TraceEvent
from app.agent.loop import AgentLoop
from app.backend.errors import BackendError
from app.backend.models import Customer, Outlet
from app.domain.messages import Message
from app.domain.results import ToolResult
from app.domain.state import ActiveOrder, Clock
from app.guards.base import Guard
from app.session.context_builder import build_context
from app.session.prompts import FALLBACK_REPLIES, system_prompt
from app.session.summary import TurnSummary, render_summary, split_turns, summarise_turn
from app.tools.base import ToolContext

logger = logging.getLogger(__name__)

Status = Literal["open", "placed", "abandoned"]


class SessionClosed(Exception):
    """The order was placed or the customer left: this chat takes no more messages."""


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
        loop: AgentLoop,
        ctx: ToolContext,
        guard: Guard,
        clock: Clock,
        summary_turns: int,
        menu_outline: str = "",
        outlet: Outlet | None = None,
    ) -> None:
        self.history: list[Message] = []
        self.tokens_used = 0
        self._abandoned = False
        self._loop = loop
        self._ctx = ctx
        self._guard = guard
        self._clock = clock
        self._summary_turns = summary_turns
        self._menu_outline = menu_outline  # the menu outline, fixed for this chat
        self._outlet = outlet
        self.summary: list[TurnSummary] = []

    @property
    def order(self) -> ActiveOrder:
        return self._ctx.order

    @property
    def customer(self) -> Customer | None:
        """Who is ordering, once they have given a phone number."""
        return self._ctx.caller.customer

    @property
    def status(self) -> Status:
        """`placed` once the order is confirmed, `abandoned` once the customer left."""
        if self._ctx.order.placed:
            return "placed"
        return "abandoned" if self._abandoned else "open"

    def abandon(self) -> None:
        """The customer left or timed out. Cancels the draft so it is not left open on the
        server. Safe to repeat; a placed order is left alone."""
        if self.status != "open":
            return
        self._abandoned = True
        order_id = self._ctx.order.order_id
        if order_id is None:
            return
        try:
            self._ctx.order.latest = self._ctx.backend.cancel_order(order_id)
        except BackendError:
            logger.warning("Could not cancel order %s when its chat ended", order_id)

    def act(self, tool: str, args: dict[str, Any]) -> ToolResult:
        """Run a tool for a touch on the kiosk screen, with no model call. The order the chat
        shows the model comes from the same state, so the next message already sees the change."""
        if self.status != "open":
            raise SessionClosed(self.status)
        return self._loop.act(tool, args, self._ctx)

    def send(
        self, text: str, *, spoken: bool = False, on_text: Callable[[str], None] | None = None
    ) -> Reply:
        """Answer one customer message. `spoken` marks dictated text that will be read aloud.
        With `on_text`, reply text is passed on as it is written, before the turn ends."""
        if self.status != "open":
            raise SessionClosed(self.status)
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
            text=build_context(now, self._ctx.order, self._ctx.caller, earlier, spoken),
        )
        result = self._loop.run(
            system_prompt(self._menu_outline, self._outlet),
            [*messages, context, user],
            self._ctx,
            events.append,
            on_text,
        )

        self.tokens_used += sum(
            e.input_tokens + e.output_tokens for e in events if isinstance(e, LLMCalled)
        )
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

    def _context(self) -> tuple[str, list[Message]]:
        """History as the model sees it: of the last k turns before the latest, those that called
        tools become summary entries and chat-only ones stay word for word (they are cheap, and an
        answer stays next to its question). The latest turn is always word for word."""
        turns = split_turns(self.history)
        if not turns:
            return "", []
        earlier, latest = turns[:-1], turns[-1]
        recent = range(max(0, len(earlier) - self._summary_turns), len(earlier))
        summarised = [self.summary[i] for i in recent if self.summary[i].used_tools]
        verbatim = [m for i in recent if not self.summary[i].used_tools for m in earlier[i]]
        return render_summary(summarised), [*verbatim, *latest]
