"""Shared by the supervisor's two calls: how the order, the customer, the items and the history are
shown to the model. Nothing here shows a price or a total: those are added to the reply by code."""

import json

from app.agent.items import HELD, LOOKUP_DOWN, Item
from app.agent.state import State, Turn
from app.backend.models import Line, Order, allergies_on_file
from app.llm.messages import Message
from app.menu.names import dish_name, option_name

FALLBACK = {
    "llm_error": "Sorry, I can't reach the system right now. Please try again in a moment.",
    "unclear": "Sorry, I didn't catch that. Could you say it again?",
}


def history_messages(history: list[Turn]) -> list[Message]:
    messages: list[Message] = []
    for turn in history:
        messages += [
            Message(role="user", text=turn.user),
            Message(role="assistant", text=turn.reply),
        ]
    return messages


def _line(line: Line) -> str:
    parts = [f"{line.quantity} x {dish_name(line.name)}"]
    if line.meal_size:
        parts.append(f"{line.meal_size} meal")
    parts += [option_name(o["name"]) for o in line.options]
    if line.note:
        parts.append(f"note: {line.note}")
    return f"line {line.id}: {', '.join(parts)}"


def render_order(order: Order | None) -> str:
    if order is None or not order.lines:
        return "Your order: empty."
    heading = "Your order"
    if order.status == "confirmed":
        heading = "Your order, PLACED"
    return "\n".join([f"{heading}:", *map(_line, order.lines)])


def render_people(state: State) -> list[str]:
    """Who is ordering and what must limit every suggestion."""
    customer = state.get("customer")
    lines = []
    if customer is not None:
        lines.append(f"Customer: {customer.name or 'identified, no name given'}")
        if usual := state.get("usual"):
            lines.append(f"Usually orders: {', '.join(usual)}")
    on_file = allergies_on_file(customer)
    avoid = [*on_file, *(a for a in state.get("allergies", []) if a not in on_file)]
    said = [f"allergic to {', '.join(avoid)}"] if avoid else []
    said += ["vegetarian only"] if state.get("veg_only") else []
    if said:
        lines.append(f"Needs: {'; '.join(said)}")
    return lines


def _row(item: Item) -> dict[str, object]:
    row: dict[str, object] = {
        "id": item.id,
        "kind": item.kind,
        "dish_text": item.dish_text,
        "qty": item.qty,
        "status": item.status,
    }
    if item.question:
        row["question"] = item.question
    if item.candidates:
        row["candidates"] = item.candidates
    return row


def render_items(items: list[Item]) -> str:
    """One JSON line per open item, for the model that decides what the customer meant."""
    return "\n".join(json.dumps(_row(i)) for i in items)


def _order_state(order: Order | None) -> str:
    if order is None:
        return "ORDER: nothing has been ordered yet."
    state = {"draft": "open and NOT placed yet", "confirmed": "placed", "cancelled": "cancelled"}
    names = ", ".join(dict.fromkeys(dish_name(ln.name) for ln in order.lines))
    on_it = f" Dishes on it: {names}." if names else " It has no dishes."
    return f"ORDER: {state.get(order.status, order.status)}.{on_it}"


def _doing(item: Item) -> str:
    what = {
        "add": f"adding {item.dish_text or 'that dish'}",
        "remove": "removing that item",
        "change_qty": "changing that amount",
        "place": "placing the order",
        "cancel": "cancelling the order",
        "phone": "saving the phone number",
        "need": "noting that",
    }
    return what.get(item.kind, "the lookup")


def _done(item: Item) -> str | None:
    r = item.result if isinstance(item.result, dict) else {}
    match item.kind:
        case "add":
            return f"DONE: added {r.get('added', item.dish_text)}."
        case "remove":
            return f"DONE: removed {r.get('removed', 'that item')}."
        case "change_qty":
            return f"DONE: changed the amount of {r.get('changed', 'that item')}."
        case "place":
            return "DONE: the order is placed."
        case "cancel":
            return "DONE: the order is cancelled."
        case "phone":
            more = [f"Their name is {r['name']}."] if r.get("name") else []
            if r.get("allergies"):
                more.append(f"Allergic to {', '.join(r['allergies'])} (on file).")
            if r.get("usual_dishes"):
                more.append(
                    f"Their usual dishes: {', '.join(r['usual_dishes'])}; you may offer one."
                )
            return " ".join(["DONE: saved the customer's phone number.", *more])
        case "need":
            noted = r.get("noted", {})
            said = (
                [f"allergic to {', '.join(noted['allergies'])}"] if noted.get("allergies") else []
            )
            said += ["eats only vegetarian food"] if noted.get("veg_only") else []
            return f"DONE: noted that the customer is {' and '.join(said) or 'as they said'}."
        case "show_order":
            return (
                "SHOW: the customer asked to hear their order. The system adds it right after your "
                "reply, so just introduce it in a few words."
            )
        case "search":
            return f"ANSWER: {item.result}"
        case _:
            return None  # chat: nothing happened


def ask_text(item: Item) -> str:
    """The question an open item puts to the customer, as it is said to them."""
    question = item.question or "What would you like?"
    if item.candidates and not all(c in question for c in item.candidates):
        question += f" Choices: {', '.join(item.candidates)}."
    return question


def open_questions(items: list[Item]) -> list[str]:
    """Every question this turn leaves open. Code puts them to the customer itself, after the
    model's words, so a question is never left out or put about the wrong dish."""
    return [ask_text(i) for i in items if i.status == "needs_user"]


def has_news(items: list[Item]) -> bool:
    """Whether the turn has anything to tell besides questions. If not, the model has nothing to
    say, and code puts the questions to the customer on its own."""
    return any(i.status == "failed" or (i.status == "done" and _done(i)) for i in items)


def _ask(item: Item) -> str:
    return (
        "ASK: the system asks the customer this right after your reply, so do not ask it or "
        f"repeat it: {ask_text(item)}"
    )


def _failed(item: Item) -> str:
    r = item.result if isinstance(item.result, dict) else {}
    subject = item.dish_text or "that"
    if r.get("error") == LOOKUP_DOWN:
        return (
            f"FAILED: a technical problem stopped the menu lookup, so nothing is known about "
            f"{subject}. Apologise in a few plain words and offer to try again. Do not say the "
            "dish is missing."
        )
    if r.get("error") == HELD:
        return (
            f"NOT DONE: {_doing(item)} has not happened yet, because other choices are still "
            "open. Say it will be done once those are settled."
        )
    if "not_on_the_menu" in r:
        close = r.get("alternatives") or []
        near = f" Close dishes: {', '.join(close)}." if close else " Nothing close."
        return f"NOT SOLD: {subject} is not on the menu.{near}"
    hint = f" {r['hint']}" if r.get("hint") else ""
    return f"FAILED: {_doing(item)} did not work: {r.get('error', 'it did not work')}.{hint}"


def turn_report(items: list[Item], order: Order | None) -> str:
    """What really happened this turn, as plain statements written by code from the items and the
    order. The reply is phrased from these lines alone, so it never has to read a status, an id or
    a field name, and cannot claim what no line says."""
    facts: list[str] = []
    for item in items:
        if item.status == "done":
            line = _done(item)
        elif item.status == "needs_user":
            line = _ask(item)
        elif item.status == "failed":
            line = _failed(item)
        else:
            line = None
        if line:
            facts.append(line)
    changed = any(f.startswith("DONE") for f in facts)
    closing = (
        "CHANGES: only the DONE lines above happened."
        if changed
        else "CHANGES: none. Nothing was added, removed, placed or cancelled this turn."
    )
    return "\n".join([_order_state(order), *facts, closing])
