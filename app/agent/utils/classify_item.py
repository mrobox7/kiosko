"""Turns an item's words into a status, in plain code: a dish is `ready` only when its name is
clearly the one meant (see fuzzy.py) and its choices match exactly one thing on the menu. Choices
and order lines use the matcher the tools already use."""

import re
from collections.abc import Sequence

from app.agent.items import Item
from app.backend.models import Dish, Line, Order
from app.menu.fuzzy import pick
from app.menu.lookup import LookupFailed, find_line, find_options
from app.menu.names import dish_name

# The hints that list names, as menu/lookup.py writes them; a test keeps this in step with it.
_LISTS = ("Ask the customer which one: ", "Closest: ")


def classify_item(item: Item, dishes: Sequence[Dish], order: Order | None) -> Item:
    """The item with its status (and ids) set from what it says."""
    match item.kind:
        case "chat" | "show_order":
            return _with(item, "done")
        case "place" | "cancel":
            return _with(item, "ready")
        case "search":
            return _with(item, "needs_search")
        case "add":
            return _add(item, dishes)
        case "phone":
            return _phone(item)
        case "need":
            return _with(item, "ready" if item.allergies or item.veg_only else "done")
        case _:
            return _line(item, order.lines if order else [])


def _with(item: Item, status: str, **changes: object) -> Item:
    cleared: dict[str, object] = {"question": None, "candidates": []}
    return item.model_copy(update={"status": status, **cleared, **changes})


def _ask(item: Item, question: str, candidates: list[str] | None = None) -> Item:
    return item.model_copy(
        update={"status": "needs_user", "question": question, "candidates": candidates or []}
    )


def _names(problem: LookupFailed) -> list[str]:
    for lead in _LISTS:
        if problem.hint.startswith(lead):
            return problem.hint.removeprefix(lead).split(", ")
    return []


def _refused(item: Item, problem: LookupFailed) -> Item:
    return _ask(item, f"{problem.message}. {problem.hint}", _names(problem))


def _phone(item: Item) -> Item:
    """A number is only taken once it has been read back and the customer said it is right."""
    digits = re.sub(r"\D", "", item.phone or "")
    if not digits:
        return _ask(item, "What is your mobile number?")
    if not item.digits_confirmed:
        return _ask(item, f"I heard {' '.join(digits)}. Is that right?")
    return _with(item, "ready")


def _which(said: str, names: list[str]) -> str:
    """The question for several dishes that fit what was said: a kind of dish they all are ("burger")
    or a near miss ("diet coke")."""
    squash = str.maketrans("", "", " -")
    key = said.lower().translate(squash)
    listed = f"{', '.join(names[:-1])} or {names[-1]}" if len(names) > 1 else names[0]
    if len(names) > 1 and all(key in n.lower().translate(squash) for n in names):
        return f"We have a few {said} options: {listed}. Which one would you like?"
    return f"Do you mean {listed}?"


def _add(item: Item, dishes: Sequence[Dish]) -> Item:
    if not item.dish_text:
        return _ask(item, "Which dish would you like?")
    verdict = pick(item.dish_text, dishes)
    if verdict.kind == "none":
        return _with(item, "needs_search")  # not a name: the searcher may know what is meant
    if verdict.dish is None:
        names = [dish_name(d.name) for d in verdict.candidates]
        return _ask(item, _which(item.dish_text, names), names)
    options, size = item.options, item.meal_size
    if size and not verdict.dish.meal_offers:  # no meal here, so "Medium" can only be a choice
        options, size = [*options, size], None
    try:
        ids = find_options(verdict.dish, options, size) if options else []
    except LookupFailed as problem:
        return _refused(item, problem)
    return _with(
        item, "ready", dish_id=verdict.dish.id, option_ids=ids, options=options, meal_size=size
    )


def _line(item: Item, lines: Sequence[Line]) -> Item:
    if item.target_line is not None and any(ln.id == item.target_line for ln in lines):
        return _with(item, "ready")
    shown = [f"line {ln.id}: {dish_name(ln.name)}" for ln in lines]
    if not item.dish_text:
        return _ask(item, "Which item on your order?", shown)
    try:
        found = find_line(lines, item.dish_text)
    except LookupFailed as problem:
        return _ask(item, f"{problem.message}. {problem.hint}", shown)
    return _with(item, "ready", target_line=found.id)
