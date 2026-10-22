"""Builders for contexts, loops and sessions wired to the fake ordering server."""

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.agent.loop import AgentLoop
from app.backend.client import BackendClient
from app.backend.models import Outlet
from app.domain.messages import Message
from app.guards.rules import RulesGuard
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM, LLMCall
from app.menu.menu import Menu
from app.session.factory import Runtime
from app.session.session import Session
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.support.fake_order_server import FakeOrderServer

NOW = datetime(2030, 6, 1, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
OUTLET = "JPR-013-7429"
OUTLET_INFO = Outlet(
    code=OUTLET, name="McDonald's Nemi Nagar", address="Gandhi Path West, Vaishali Nagar, Jaipur"
)


def clock() -> datetime:
    return NOW


def make_ctx(server: FakeOrderServer | None = None) -> ToolContext:
    """A tool context on the fake server, with the menu already loaded, so the requests a test
    records are the tools' own."""
    server = server or FakeOrderServer()
    http = httpx.Client(base_url="http://shop", transport=httpx.MockTransport(server.handle))
    backend = BackendClient(http)
    menu = Menu(backend, OUTLET)
    menu.refresh()
    server.requests.clear()
    return ToolContext(backend=backend, clock=clock, outlet_code=OUTLET, menu=menu)


def make_order_tools() -> tuple[ToolContext, FakeOrderServer, ToolRegistry]:
    server = FakeOrderServer()
    return make_ctx(server), server, ToolRegistry.discover()


def make_runtime(llm: FakeLLM, server: FakeOrderServer | None = None, **speech: object) -> Runtime:
    """What the API runs on: the fake model, the fake ordering server and its menu."""
    ctx = make_ctx(server or FakeOrderServer())
    return Runtime(
        backend=ctx.backend,
        loop=make_loop(llm),
        clock=clock,
        menu=ctx.menu,
        outlet=OUTLET_INFO,
        **speech,  # type: ignore[arg-type]
    )


def make_loop(llm: FakeLLM, **kw: int) -> AgentLoop:
    return AgentLoop(
        llm,
        ToolRegistry.discover(),
        max_iterations=kw.get("max_iterations", 8),
        max_tool_calls=kw.get("max_tool_calls", 12),
        tool_result_max_chars=kw.get("max_chars", 4000),
    )


def make_session(
    steps: Sequence[LLMResponse | Exception],
    server: FakeOrderServer | None = None,
    **guard: int,
) -> tuple[Session, FakeLLM, FakeOrderServer]:
    server = server or FakeOrderServer()
    llm = FakeLLM(steps)
    session = Session(
        loop=make_loop(llm),
        ctx=make_ctx(server),
        guard=RulesGuard(
            max_chars=guard.get("max_chars", 1000),
            turns_per_min=guard.get("turns_per_min", 10),
            token_budget=guard.get("token_budget", 200_000),
        ),
        clock=clock,
        summary_turns=guard.get("summary_turns", 3),
    )
    return session, llm, server


def context_of(call: LLMCall) -> str:
    """The context message the model was given right before the customer's message."""
    return next(m.text for m in reversed(call.messages) if m.role == "system" and m.text)


def chat_texts(messages: Sequence[Message]) -> list[tuple[str, str]]:
    """(role, text) of the chat itself, without the per-turn context messages."""
    return [(m.role, m.text or "") for m in messages if m.role != "system"]
