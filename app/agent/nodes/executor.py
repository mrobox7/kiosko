"""The executor: runs the clear items through the order tools, in the order the customer said them.
No model: a ready item already holds the ids its tool needs. One item failing does not stop the
ones after it. A place or cancel that has to wait for an open question is not run and not kept: it
is reported as not done, so a later turn never places an order the customer may have changed."""

import time
from typing import Any

from app.agent.items import HELD, Item
from app.agent.router import runnable
from app.agent.services import Services
from app.agent.state import State
from app.agent.tool_context import state_of, tool_context
from app.agent.trace import ActionRun, TraceEvent
from app.backend.models import Order
from app.menu.names import dish_name
from app.tools.contract import ToolResult
from app.tools.registry import ToolRegistry

HELD_RESULT = {"error": HELD}


def call_of(item: Item) -> tuple[str, dict[str, Any]]:
    """The tool and arguments for a ready item."""
    match item.kind:
        case "add":
            args: dict[str, Any] = {
                "dish_id": item.dish_id,
                "quantity": item.qty,
                "options": [{"option_id": i} for i in item.option_ids],
            }
            if item.meal_size:
                args["meal_size"] = item.meal_size
            if item.note:
                args["note"] = item.note
            return "add_to_order", args
        case "remove":
            return "remove_from_order", {"line_id": item.target_line}
        case "change_qty":
            return "change_quantity", {"line_id": item.target_line, "quantity": item.qty}
        case "place":
            return "place_order", {}
        case "phone":
            return "set_customer", {"phone": item.phone, "digits_confirmed": True}
        case "need":
            return "note_need", {"allergies": item.allergies, "veg_only": item.veg_only}
        case _:
            return "cancel_order", {}


def _line_name(order: Order | None, line_id: int | None) -> str:
    found = [ln.name for ln in order.lines if ln.id == line_id] if order else []
    return dish_name(found[0]) if found else "the item"


def _compact(item: Item, data: Any, before: Order | None) -> dict[str, Any]:
    """What became of a done item, with no quantity, price or total in it: the reply is written
    from this, and those numbers are added to the reply by code."""
    match item.kind:
        case "add":
            return {"added": dish_name(data["added"]["name"])}
        case "remove":
            return {"removed": dish_name(data["removed"]["name"])}
        case "change_qty":
            return {"changed": _line_name(before, item.target_line)}
        case "place":
            return {"placed": True}
        case "cancel":
            return {"cancelled": True}
        case "phone":
            keys = ("name", "allergies", "usual_dishes")
            return {"identified": True, **{k: data[k] for k in keys if k in data}}
        case _:
            return {"noted": {"allergies": data["allergies"], "veg_only": data["veg_only"]}}


def _outcome(item: Item, result: ToolResult, before: Order | None) -> Item:
    if result.ok:
        return item.model_copy(
            update={"status": "done", "result": _compact(item, result.data, before)}
        )
    error = result.error
    assert error is not None
    if error.code == "incomplete":  # a question the server needs answered, not a failure
        question = error.hint or error.message
        return item.model_copy(update={"status": "needs_user", "question": question})
    reason = {"error": error.message, "hint": error.hint}
    return item.model_copy(update={"status": "failed", "result": reason})


def _event(item: Item, started: float) -> ActionRun:
    summary = "ok" if item.status == "done" else str(item.question or item.result or "")
    return ActionRun(item.kind, item.status, summary, int((time.monotonic() - started) * 1000))


def executor(state: State, services: Services) -> dict[str, object]:
    ctx = tool_context(state, services)
    all_items = state.get("items", [])
    now = {id(i) for i in runnable(all_items)}
    items: list[Item] = []
    events: list[TraceEvent] = []
    for item in all_items:
        started = time.monotonic()
        if item.status != "ready":
            items.append(item)
            continue
        if id(item) not in now:
            held = item.model_copy(update={"status": "failed", "result": HELD_RESULT})
            items.append(held)
            events.append(_event(held, started))
            continue
        name, args = call_of(item)
        before = ctx.order
        result = ToolRegistry.shared().dispatch(name, args, ctx)
        ctx = ctx.after(result.update)
        done = _outcome(item, result, before)
        items.append(done)
        events.append(_event(done, started))
    return {"items": items, "events": events, **state_of(ctx)}
