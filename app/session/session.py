"""One chat, over the graph: sends the customer's messages in, reads the order and status out, and
runs the taps on the kiosk screen. The chat's state lives in the graph's saver, keyed by the
session's thread id; nothing about the chat is held here."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import Graph
from app.agent.services import Services
from app.agent.state import Input, State
from app.agent.tool_context import run_tool, state_of, tool_context
from app.agent.trace import TraceEvent
from app.backend.errors import BackendError
from app.backend.models import Customer, Order
from app.tools.contract import ToolResult

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
    """One chat. The API holds a lock around it, so it handles one request at a time."""

    def __init__(
        self, graph: Graph, saver: InMemorySaver, services: Services, thread_id: str
    ) -> None:
        self._graph = graph
        self._saver = saver
        self._services = services
        self._thread_id = thread_id
        self._final: Status | None = None  # the status the chat ended with, once closed
        self._config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        start: Input = {"kind": "start"}
        graph.invoke(start, self._config)

    def _state(self) -> State:
        return cast(State, self._graph.get_state(self._config).values)

    @property
    def order(self) -> Order | None:
        """The order as the ordering server last reported it; None until the first dish."""
        return self._state().get("order")

    @property
    def customer(self) -> Customer | None:
        """Who is ordering, once they have given a phone number."""
        return self._state().get("customer")

    @property
    def status(self) -> Status:
        return self._final or self._state().get("status", "open")

    def abandon(self) -> None:
        """The customer left or timed out. Cancels the draft so it is not left open on the
        server. Safe to repeat; a placed order is left alone."""
        state = self._state()
        if state.get("status", "open") != "open":
            return
        changes: dict[str, Any] = {"status": "abandoned"}
        order = state.get("order")
        if order is not None:
            try:
                changes["order"] = self._services.backend.cancel_order(order.id)
            except BackendError:
                logger.warning("Could not cancel order %s when its chat ended", order.id)
        self._graph.update_state(self._config, changes, as_node="commit")

    def close(self) -> None:
        """Forget the chat's saved state. The chat keeps its final status."""
        self._final = self.status
        self._saver.delete_thread(self._thread_id)

    def act(self, tool: str, args: dict[str, Any]) -> ToolResult:
        """Run a tool for a touch on the kiosk screen, with no model call and no history entry.
        The state is updated the way a turn would, so the next message already sees the change."""
        state = self._state()
        if (status := state.get("status", "open")) != "open":
            raise SessionClosed(status)
        result, ctx = run_tool(tool, args, tool_context(state, self._services))
        changes = state_of(ctx)
        if tool == "place_order" and result.ok:
            changes |= {"status": "placed", "items": []}
        self._graph.update_state(self._config, changes, as_node="commit")
        return result

    def send(
        self, text: str, *, spoken: bool = False, on_text: Callable[[str], None] | None = None
    ) -> Reply:
        """Answer one customer message. `spoken` marks dictated text that will be read aloud.
        With `on_text`, reply text is passed on as it is written, before the turn ends."""
        if (status := self.status) != "open":
            raise SessionClosed(status)
        message: Input = {"kind": "message", "user_text": text, "spoken": spoken}
        out = self._graph.invoke(
            message,
            self._config,
            context={"on_text": on_text} if on_text else None,
        )
        return Reply(
            text=out["reply"].strip(), events=out["events"], stop_reason=out["stop_reason"]
        )
