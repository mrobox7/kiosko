"""Print what a scripted order sends to the model, call by call, with token counts.

    curl 'http://localhost:8010/catalog?outlet=JPR-013-7429' -o catalog.json
    uv run --with tiktoken python -m tests.show_request catalog.json [--call N | --all]

Offline: the model is a script and the ordering server is the test stand-in. Only the menu is
real, so the menu outline, the dish names and the tool replies about dishes are the outlet's own.
The cart lines and prices come from the stand-in and are not the menu's. By default it prints the
summary table and the last call in full; `--call N` prints call N and `--all` every call.
`reused` is how many of a call's input tokens a provider that caches the start of the request could
take from the call before it. It assumes the usual order (tool definitions, system message, then the
messages) and counts whole items, so the real figure can be a little higher.
Token counts use `o200k_base`, close to the model's own count (the provider's can differ by
10 to 15%).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from app.agent.loop import AgentLoop
from app.backend.client import BackendClient
from app.config.settings import Settings
from app.domain.messages import ToolCall
from app.guards.rules import RulesGuard
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM, LLMCall
from app.llm.openai_compat import OpenAICompatLLM
from app.menu.menu import Menu
from app.session.session import Session
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.support.builders import OUTLET, OUTLET_INFO, clock
from tests.support.fake_order_server import MENU, FakeOrderServer

COMPACT = (",", ":")


def tokenizer() -> Any:
    try:
        import tiktoken
    except ImportError:
        sys.exit("Needs a tokenizer: uv run --with tiktoken python -m tests.show_request ...")
    return tiktoken.get_encoding("o200k_base")


def pick(menu: Menu, *hints: str) -> str:
    """The first dish whose name has one of the hints, else the first dish on the menu."""
    for hint in hints:
        for dish in menu.dishes:
            if hint.lower() in dish.name.lower():
                return dish.name
    return menu.dishes[0].name


def tool(name: str, **args: object) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"call_{name}", name=name, arguments=dict(args))])


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def scenario(menu: Menu, server: FakeOrderServer) -> list[tuple[str, list[LLMResponse]]]:
    """The customer's messages, each with the replies the scripted model gives to it."""
    dessert = pick(menu, "McFlurry Oreo", "McFlurry", "Sundae")
    burger = pick(menu, "McAloo Tikki", "McVeggie", "Burger")
    server.next_name = burger  # what the stand-in calls the line the customer adds
    return [
        (
            "Hi, what desserts do you have?",
            [say(f"We have sundaes and McFlurries, like {dessert}.")],
        ),
        (
            f"How many calories in the {dessert}?",
            [
                tool("get_item", dish=dessert, info="nutrition"),
                say("That figure is an estimate, not official."),
            ],
        ),
        (f"One {burger} please", [tool("add_to_order", dish=burger), say("Added. Anything else?")]),
        ("Make it two", [tool("change_quantity", line_id=10, quantity=2), say("Two now.")]),
        ("That's all", [say("That is 2 of them. Shall I place the order?")]),
        ("Yes", [tool("place_order"), say("Placed. Your order number is 14.")]),
    ]


def run(catalog: Path) -> list[LLMCall]:
    """Play the scenario against the real menu and return every call the model received."""
    server = FakeOrderServer()
    body = json.loads(catalog.read_text())

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"version": body["version"]})
        if request.url.path == "/catalog":
            return httpx.Response(200, json=body)
        if request.method == "POST" and request.url.path.endswith("/lines"):
            # The stand-in only knows its own few dishes: give any other dish a price.
            MENU.setdefault(json.loads(request.content)["product_id"], ("Dish", 80.0))
        return server.handle(request)

    backend = BackendClient(
        httpx.Client(base_url="http://shop", transport=httpx.MockTransport(handle))
    )
    menu = Menu(backend, OUTLET)
    menu.refresh()
    turns = scenario(menu, server)
    llm = FakeLLM([step for _, steps in turns for step in steps])
    settings = Settings(_env_file=None)  # the defaults, whatever .env says
    session = Session(
        loop=AgentLoop(
            llm,
            ToolRegistry.discover(),
            max_iterations=settings.max_iterations,
            max_tool_calls=settings.max_tool_calls_per_turn,
            tool_result_max_chars=settings.tool_result_max_chars,
        ),
        ctx=ToolContext(backend=backend, clock=clock, outlet_code=OUTLET, menu=menu),
        guard=RulesGuard(
            max_chars=settings.max_message_chars,
            turns_per_min=settings.rate_limit_turns_per_min,
            token_budget=settings.session_token_budget,
        ),
        clock=clock,
        summary_turns=settings.summary_turns,
        menu_outline=menu.outline,
        outlet=OUTLET_INFO,
    )
    for text, _ in turns:
        reply = session.send(text)
        if reply.stop_reason != "answered":
            sys.exit(f"The scripted order stopped on {text!r}: {reply.stop_reason} {reply.text}")
    return llm.calls


def wire(call: LLMCall) -> dict[str, Any]:
    """The request body as it goes to the provider."""
    return OpenAICompatLLM(None, "model", max_output_tokens=1024)._request(  # type: ignore[arg-type]
        call.system, call.messages, call.tools
    )


def counts(call: LLMCall, count: Any) -> dict[str, int]:
    body = wire(call)
    rest = body["messages"][1:]  # after the system message
    context = [m for m in rest if m["role"] == "system"]
    others = [m for m in rest if m["role"] != "system"]
    parts = {
        "system": count(call.system),
        "tools": count(json.dumps(body["tools"], separators=COMPACT)),
        "context": count(json.dumps(context, separators=COMPACT)),
        "messages": count(json.dumps(others, separators=COMPACT)),
    }
    return {**parts, "total": sum(parts.values())}


def prefix_items(call: LLMCall) -> list[str]:
    """The request as the items a provider reads in order: tools, system message, messages."""
    body = wire(call)
    messages = [json.dumps(m, ensure_ascii=False) for m in body["messages"][1:]]
    return [json.dumps(body["tools"], separators=COMPACT), call.system, *messages]


def reused(previous: LLMCall | None, call: LLMCall, count: Any) -> int:
    """Tokens in the leading items that are the same as in the previous call."""
    if previous is None:
        return 0
    tokens = 0
    for before, now in zip(prefix_items(previous), prefix_items(call), strict=False):
        if before != now:
            break
        tokens += count(now)
    return tokens


def show_table(calls: list[LLMCall], count: Any) -> None:
    head = (
        f"{'call':>4} {'system':>7} {'tools':>7} {'context':>8} {'messages':>9} {'total':>7} "
        f"{'reused':>7}"
    )
    print(head + "\n" + "-" * len(head))
    sums = dict.fromkeys(("system", "tools", "context", "messages", "total", "reused"), 0)
    for number, call in enumerate(calls, 1):
        c = {
            **counts(call, count),
            "reused": reused(calls[number - 2] if number > 1 else None, call, count),
        }
        for key in sums:
            sums[key] += c[key]
        print(
            f"{number:>4} {c['system']:>7} {c['tools']:>7} {c['context']:>8} "
            f"{c['messages']:>9} {c['total']:>7} {c['reused']:>7}"
        )
    print("-" * len(head))
    print(
        f"{'all':>4} {sums['system']:>7} {sums['tools']:>7} {sums['context']:>8} "
        f"{sums['messages']:>9} {sums['total']:>7} {sums['reused']:>7}   "
        f"input tokens over {len(calls)} calls"
    )
    print(
        "\nsystem = prompt + outlet + menu outline; tools = the 10 definitions; context = the "
        "per-turn context message;\nmessages = earlier turns, the customer's words and this "
        "turn's tool calls and results."
    )


def show_call(number: int, call: LLMCall, count: Any) -> None:
    body = wire(call)
    c = counts(call, count)
    print(f"\n{'=' * 78}\nCALL {number}: {c['total']} input tokens\n{'=' * 78}")
    print(f"\n--- SYSTEM MESSAGE ({c['system']} tokens)\n{call.system}")
    print(f"\n--- TOOL DEFINITIONS ({c['tools']} tokens)")
    for definition in body["tools"]:
        text = json.dumps(definition, separators=COMPACT)
        print(f"{definition['function']['name']:>18}  {count(text):>4} tokens")
    print("\n--- MESSAGES")
    for message in body["messages"][1:]:
        text = json.dumps(message, ensure_ascii=False)
        print(f"\n[{message['role']}] {count(text)} tokens\n{text}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("catalog", type=Path, help="a saved GET /catalog response")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--call", type=int, help="print this call in full")
    which.add_argument("--all", action="store_true", help="print every call in full")
    args = parser.parse_args()
    encoding = tokenizer()

    def count(text: str) -> int:
        return len(encoding.encode(text))

    calls = run(args.catalog)
    show_table(calls, count)
    chosen = range(1, len(calls) + 1) if args.all else [args.call if args.call else len(calls)]
    for number in chosen:
        if not 1 <= number <= len(calls):
            sys.exit(f"There are {len(calls)} calls; asked for {number}")
        show_call(number, calls[number - 1], count)


if __name__ == "__main__":
    main()
