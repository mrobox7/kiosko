"""The searcher: finds out what a vague or unknown request means, with the menu tools the model
calls natively. It ends by calling `finish`. It never makes an item `ready`: even one match is put
to the customer as a question."""

import logging
import time
from functools import cache

from pydantic import BaseModel, Field, ValidationError

from app.agent.items import LOOKUP_DOWN, Item
from app.agent.prompts import SEARCHER_PROMPT
from app.agent.services import Services
from app.agent.state import State
from app.agent.tool_context import tool_context
from app.agent.trace import ActionRun, Tally, TraceEvent
from app.llm.contract import LLMError, LLMResponse
from app.llm.messages import Message, ToolCall, ToolOutcome, ToolSpec
from app.llm.tool_spec import spec_of
from app.menu.lookup import LookupFailed, find_dish
from app.menu.names import dish_name
from app.tools.contract import ToolContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 2
NOT_FOUND = "I couldn't find that on the menu. Could you tell me which dish you mean?"
MENU_TOOLS = {
    "get_menu": "Find dishes. With no arguments it lists the sections. `text` finds dishes by name, "
    "best match first, each with a dish_id and a match score. The other fields narrow by section, "
    "diet, price, nutrition or allergen.",
    "get_item": "Look at one dish by its menu name: price, choices, nutrition or allergens.",
}


class Final(BaseModel):
    answer: str
    candidates: list[str] = Field(default_factory=list)
    available: bool = True  # false: the dish is not on the menu and candidates are alternatives


@cache
def _menu_specs() -> list[ToolSpec]:
    return [spec_of(n, d, ToolRegistry.shared().args_schema(n)) for n, d in MENU_TOOLS.items()]


FINISH = spec_of(
    "finish",
    "Give the final answer. For a question about the menu, `answer` is the answer. For a dish to "
    "order that is on the menu, `answer` is one short question asking which one and `candidates` "
    "are the menu names that could be meant. For a dish that is not on the menu, set `available` "
    "to false, say so in `answer`, and put the closest menu names in `candidates`.",
    Final.model_json_schema(),
)


def _final_of(response: LLMResponse) -> Final | None:
    for call in response.tool_calls:
        if call.name == "finish" and call.parse_error is None:
            try:
                return Final.model_validate(call.arguments)
            except ValidationError:
                return None
    return None


def _run(call: ToolCall, ctx: ToolContext) -> ToolOutcome:
    """The answer to one tool call. A call the searcher may not make is answered with an error,
    because every call the model made has to be answered."""
    if call.parse_error or call.name not in MENU_TOOLS:
        reason = call.parse_error or f"Use {', '.join(MENU_TOOLS)} or finish with an answer."
        return ToolOutcome(call_id=call.id, content=f'{{"ok": false, "error": "{reason}"}}')
    result = ToolRegistry.shared().dispatch(call.name, call.arguments, ctx)
    return ToolOutcome(
        call_id=call.id, content=result.model_dump_json(include={"ok", "data", "error"})
    )


def _question(item: Item) -> str:
    if item.kind == "search":
        return f"The customer asks: {item.dish_text}"
    return f"The customer wants to order: {item.dish_text}"


def _settle(item: Item, final: Final, services: Services) -> Item:
    """The item once the model has answered."""
    if item.kind == "search":
        return item.model_copy(update={"status": "done", "result": final.answer})
    names: list[str] = []
    for name in final.candidates:  # only names that are really on the menu
        try:
            shown = dish_name(find_dish(services.menu.dishes, name).name)
        except LookupFailed:
            continue
        if shown not in names:
            names.append(shown)
    if not final.available:  # nothing to choose between: tell the customer, and go on without it
        reason = {"not_on_the_menu": final.answer, "alternatives": names}
        return item.model_copy(update={"status": "failed", "result": reason})
    question = final.answer or NOT_FOUND
    return item.model_copy(
        update={"status": "needs_user", "question": question, "candidates": names}
    )


def _search(item: Item, ctx: ToolContext, services: Services, tally: Tally) -> Item:
    system = SEARCHER_PROMPT  # no menu card: it must look, with the tools
    messages = [Message(role="user", text=_question(item))]
    for round_ in range(MAX_TOOL_ROUNDS + 1):
        last = round_ == MAX_TOOL_ROUNDS  # the last round can only be the answer
        tools = [FINISH] if last else [*_menu_specs(), FINISH]
        try:
            response = tally.complete(services.llm, system, messages, tools, require_tool=True)
        except LLMError as exc:
            logger.warning("Search call failed: %s", exc)
            return item.model_copy(update={"status": "failed", "result": {"error": LOOKUP_DOWN}})
        final = _final_of(response)
        if final is not None:
            return _settle(item, final, services)
        if last or not response.tool_calls:
            break
        messages += [
            Message(role="assistant", text=response.text, tool_calls=response.tool_calls),
            Message(role="user", tool_outcomes=[_run(c, ctx) for c in response.tool_calls]),
        ]
    return item.model_copy(update={"status": "needs_user", "question": NOT_FOUND, "candidates": []})


def searcher(state: State, services: Services) -> dict[str, object]:
    ctx = tool_context(state, services)
    tally, events = Tally(), []
    items: list[Item] = []
    for item in state.get("items", []):
        if item.status != "needs_search":
            items.append(item)
            continue
        started = time.monotonic()
        found = _search(item, ctx, services, tally)
        items.append(found)
        summary = str(found.question or found.result or "")
        ms = int((time.monotonic() - started) * 1000)
        events.append(ActionRun("search", found.status, summary, ms))
    all_events: list[TraceEvent] = [*tally.events, *events]
    return {"items": items, "events": all_events, "tokens_used": tally.tokens}
