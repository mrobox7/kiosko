"""The supervisor's first call: what the customer wants, as a list of items. Code then sets each
item's status; the model never writes an id or a status."""

import logging

from pydantic import ValidationError

from app.agent.context import FALLBACK, history_messages, render_items, render_order, render_people
from app.agent.items import OPEN, Item, Understanding
from app.agent.prompts import MENU_HEADING, SUPERVISOR_PROMPT
from app.agent.router import next_step
from app.agent.services import Services
from app.agent.state import State
from app.agent.trace import ItemsRecorded, Tally
from app.agent.utils.classify_item import classify_item
from app.backend.models import Order
from app.llm.contract import LLMError, LLMResponse
from app.llm.messages import Message
from app.llm.tool_spec import spec_of
from app.menu.card import render_card
from app.menu.menu import Menu

logger = logging.getLogger(__name__)

TRIES = 2


RECORD = "record_request"
RECORD_SPEC = spec_of(
    RECORD,
    "Record what the customer asked for in their latest message. Call it exactly once.",
    Understanding.model_json_schema(),
)


def read(response: LLMResponse) -> Understanding | None:
    """What the model recorded, or None if it did not call the tool with the shape asked for."""
    for call in response.tool_calls:
        if call.name == RECORD and call.parse_error is None:
            try:
                return Understanding.model_validate(call.arguments)
            except ValidationError:
                return None
    return None


def apply(
    open_items: list[Item], result: Understanding, menu: Menu, order: Order | None, turn: int
) -> list[Item]:
    """The open items with the model's edits made, then the new ones, each given its status."""
    items = {i.id: i for i in open_items}
    for edit in result.updates:
        found = items.get(edit.id)
        if found is None:
            continue
        if edit.drop:
            del items[edit.id]
        else:
            changes = edit.model_dump(exclude={"id", "drop"}, exclude_none=True)
            items[edit.id] = classify_item(found.model_copy(update=changes), menu.dishes, order)
    new = [
        classify_item(Item(id=f"{turn}.{n}", **draft.model_dump()), menu.dishes, order)
        for n, draft in enumerate(result.items, 1)
    ]
    return [*items.values(), *new]


def _context(state: State, open_items: list[Item]) -> str:
    parts = [render_order(state.get("order")), *render_people(state)]
    if open_items:
        parts.append("Open items:\n" + render_items(open_items))
    return "\n\n".join(parts)


def supervisor(state: State, services: Services) -> dict[str, object]:
    open_items = [i for i in state.get("items", []) if i.status in OPEN]
    messages = [
        *history_messages(state.get("history", [])),
        Message(role="system", text=_context(state, open_items)),
        Message(role="user", text=state["user_text"]),
    ]
    card = render_card(services.menu.categories, services.menu.dishes)
    system = f"{SUPERVISOR_PROMPT}\n{MENU_HEADING}\n{card}"
    tally, result = Tally(), None
    for _ in range(TRIES):
        try:
            response = tally.complete(
                services.llm, system, messages, [RECORD_SPEC], require_tool=True
            )
        except LLMError as exc:
            logger.warning("Supervisor call failed: %s", exc)
            return {"reply": FALLBACK["llm_error"], "stop_reason": "llm_error", **tally.changes()}
        result = read(response)
        if result is not None:
            break
    if result is None:
        return {"reply": FALLBACK["unclear"], "stop_reason": "unclear", **tally.changes()}
    turn = state.get("turns_done", 0) + 1
    items = apply(open_items, result, services.menu, state.get("order"), turn)
    recorded = ItemsRecorded(result.language, [d.kind for d in result.items])
    alone = (
        bool(result.reply) and not result.updates and all(d.kind == "chat" for d in result.items)
    )
    return {  # a reply is kept only for an all-chat turn: one call is then the whole turn
        "items": items,
        "language": result.language,
        "reply": result.reply if alone else "",
        "stop_reason": "",
        **{**tally.changes(), "events": [*tally.events, recorded]},
    }


def after_supervisor(state: State) -> str:
    """Where `supervisor` leads: nowhere if it failed, to `commit` if it already has the reply, else
    wherever the router says."""
    if state.get("stop_reason"):
        return "end"
    if state.get("reply"):
        return "commit"
    return next_step(state.get("items", []))
