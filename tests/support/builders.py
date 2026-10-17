"""Builders for contexts, loops and sessions wired to fakes."""

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agent.loop import AgentLoop
from app.backend.models import Customer
from app.guards.rules import RulesGuard
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.session.session import Session
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.support.fake_backend import CUSTOMERS, FakeBackend

NOW = datetime(2030, 6, 1, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def clock() -> datetime:
    return NOW


def make_ctx(backend: FakeBackend | None = None, customer_id: int | None = None) -> ToolContext:
    return ToolContext(
        backend=(backend or FakeBackend()).client, customer_id=customer_id, clock=clock
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
    customer_id: int = 1,
    backend: FakeBackend | None = None,
    **guard: int,
) -> tuple[Session, FakeLLM, FakeBackend]:
    backend = backend or FakeBackend()
    llm = FakeLLM(steps)
    customer = Customer.model_validate(next(c for c in CUSTOMERS if c["id"] == customer_id))
    session = Session(
        customer=customer,
        loop=make_loop(llm),
        ctx=make_ctx(backend, customer_id),
        guard=RulesGuard(
            max_chars=guard.get("max_chars", 1000),
            turns_per_min=guard.get("turns_per_min", 10),
            token_budget=guard.get("token_budget", 200_000),
        ),
        clock=clock,
    )
    return session, llm, backend
