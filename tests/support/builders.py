"""Builders for contexts, runtimes and sessions wired to the fake ordering server."""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.agent.graph import build_graph, make_saver
from app.agent.services import Services
from app.backend.client import BackendClient
from app.backend.models import Outlet
from app.llm.contract import LLMResponse, Usage
from app.llm.messages import ToolCall
from app.menu.menu import Menu
from app.runtime import Runtime
from app.session.session import Session
from app.tools.contract import ToolContext, ToolResult
from app.tools.registry import ToolRegistry
from tests.support.fake_llm import FakeLLM, LLMCall
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


class Chat:
    """A tool context that moves on, as a chat does: `ctx` is replaced after each tool call by the
    context with that call's changes in it. Reads go to the current context."""

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    def __getattr__(self, name: str) -> Any:
        return getattr(self.ctx, name)


class ChatTools(ToolRegistry):
    """The registry for tests that call several tools in a row on one chat."""

    def dispatch(self, name: str, raw_args: dict[str, Any], ctx: Any) -> ToolResult:  # type: ignore[override]
        chat = ctx if isinstance(ctx, Chat) else None
        result = super().dispatch(name, raw_args, chat.ctx if chat else ctx)
        if chat is not None:
            chat.ctx = chat.ctx.after(result.update)
        return result


def make_order_tools() -> tuple[Chat, FakeOrderServer, ChatTools]:
    server = FakeOrderServer()
    return Chat(make_ctx(server)), server, ChatTools(ToolRegistry.discover()._tools.values())


def make_runtime(
    llm: FakeLLM,
    server: FakeOrderServer | None = None,
    *,
    max_chars: int = 1000,
    turns_per_min: int = 10,
    token_budget: int = 200_000,
    **speech: object,
) -> Runtime:
    """What the API runs on: the fake model, the fake ordering server and its menu."""
    ctx = make_ctx(server or FakeOrderServer())
    services = Services(
        backend=ctx.backend,
        menu=ctx.menu,
        llm=llm,
        clock=clock,
        outlet=OUTLET_INFO,
        max_chars=max_chars,
        turns_per_min=turns_per_min,
        token_budget=token_budget,
    )
    saver = make_saver()
    return Runtime(
        services=services,
        graph=build_graph(services, saver),
        saver=saver,
        **speech,  # type: ignore[arg-type]
    )


def make_session(
    steps: Sequence[LLMResponse | Exception],
    server: FakeOrderServer | None = None,
    **limits: Any,
) -> tuple[Session, FakeLLM, FakeOrderServer]:
    """A chat on the graph. `steps` are the scripted model replies: for each message, a plan
    (see `plan`) and then the reply text."""
    server = server or FakeOrderServer()
    llm = FakeLLM(steps)
    return make_runtime(llm, server, **limits).start_session(), llm, server


_KINDS = {
    "add_item": "add", "change_quantity": "change_qty", "remove_item": "remove",
    "place_order": "place", "cancel_order": "cancel", "set_customer": "phone",
    "note_need": "need", "browse_menu": "search", "item_info": "search",
    "read_back": "show_order", "clarify": "chat", "chat": "chat",
}  # fmt: skip
_FIELDS = {"dish": "dish_text", "quantity": "qty", "line_id": "target_line"}


def _item(action: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": _KINDS[action["type"]]}
    for key, value in action.items():
        if key != "type":
            item[_FIELDS.get(key, key)] = value
    if item["kind"] == "search":
        item.setdefault("dish_text", json.dumps({k: v for k, v in item.items() if k != "kind"}))
    return item


def plan(*actions: dict[str, Any], language: str = "en") -> LLMResponse:
    """The supervisor's scripted first reply: it calls `record_request` with one item per action.
    Each action is a dict with its `type` (the names the older planner used) and its params."""
    arguments = {"language": language, "items": [_item(a) for a in actions]}
    call = ToolCall(id="plan", name="record_request", arguments=arguments)
    return LLMResponse(tool_calls=[call], usage=Usage(input_tokens=100, output_tokens=10))


def tool_call(name: str, **arguments: Any) -> LLMResponse:
    """A scripted reply that calls one tool, as the searcher does."""
    return LLMResponse(
        tool_calls=[ToolCall(id=f"call-{name}", name=name, arguments=arguments)],
        usage=Usage(input_tokens=100, output_tokens=10),
    )


def finish(answer: str, *candidates: str, available: bool = True) -> LLMResponse:
    """The searcher's scripted last reply."""
    return tool_call("finish", answer=answer, candidates=list(candidates), available=available)


def say(text: str) -> LLMResponse:
    """The responder's scripted reply."""
    return LLMResponse(text=text, usage=Usage(input_tokens=200, output_tokens=20))


def context_of(call: LLMCall) -> str:
    """The context message the model was given right before the customer's message."""
    return next(m.text for m in reversed(call.messages) if m.role == "system" and m.text)
