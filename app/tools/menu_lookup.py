"""Turns the names the model sends into the dish and option ids the order endpoints take.

A name matches when it is the whole name, or else when its words are all in exactly one name.
Anything else is refused with the nearest names, because a wrong dish on an order is worse than
one more question."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.backend.models import DriveThruLine, MenuDish, MenuOptionGroup
from app.menu.menu import Menu
from app.menu.names import dish_name, normalise

SUGGESTED = 4


def exactly_one(a: object, b: object, names: str) -> None:
    """For argument models: a dish or option is named or numbered, never both and never neither."""
    if (a is None) == (b is None):
        raise ValueError(f"send one of {names}, not both and not neither")


class LookupFailed(Exception):
    """A name that cannot be turned into an id. `hint` says what to try instead."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


def _plural(kind: str) -> str:
    return kind + ("es" if kind.endswith("sh") else "s")


def _pick[T](
    query: str,
    candidates: Sequence[tuple[T, list[str], str]],
    kind: str,
    where: str = "",
) -> T:
    """The one candidate the query names. A candidate is (thing, names it answers to, name to show).
    Whole name first, then all-the-words-of-one-name; several matches or none are refused."""
    wanted = normalise(query)
    shown = {id(thing): label for thing, _, label in candidates}
    exact = [thing for thing, names, _ in candidates if wanted in map(normalise, names)]
    words = set(wanted.split())
    inside = [
        thing
        for thing, names, _ in candidates
        if words and words <= set(normalise(names[0]).split())
    ]
    for found in (exact, inside):
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            names_ = ", ".join(shown[id(t)] for t in found[:SUGGESTED])
            raise LookupFailed(
                f"ambiguous_{kind}",
                f"'{query}' fits several {_plural(kind)}{where}",
                f"Ask the customer which one: {names_}",
            )
    ranked = sorted(
        (c for c in candidates if words & set(normalise(c[1][0]).split())),
        key=lambda c: -len(words & set(normalise(c[1][0]).split())),
    )[:SUGGESTED]
    hint = "Closest: " + ", ".join(label for _, _, label in ranked) if ranked else "None are close"
    raise LookupFailed(f"unknown_{kind}", f"No {kind} called '{query}'{where}", hint)


def find_dish(menu: Sequence[MenuDish], name: str) -> MenuDish:
    """The dish a name stands for, from what the outlet is selling now."""
    return _pick(name, [(p, [p.name, dish_name(p.name)], dish_name(p.name)) for p in menu], "dish")


def resolve_dish(menu: Menu, name: str | None, dish_id: int | None) -> MenuDish:
    """The dish the model named or numbered. A number that is not on the menu is refused here, so
    no request is spent on it."""
    if dish_id is None:
        assert name is not None  # the arguments allow a name or a number, never neither
        return find_dish(menu.dishes, name)
    dish = menu.dish(dish_id)
    if dish is None:
        raise LookupFailed(
            "unknown_dish",
            f"No dish with id {dish_id} on the menu",
            "Use a dish_id from get_menu, or name the dish.",
        )
    return dish


def find_line(lines: Sequence[DriveThruLine], name: str) -> DriveThruLine:
    """The line of the order a name stands for. Two lines of the same dish are never guessed
    between: they are shown with their numbers."""
    return _pick(
        name,
        [
            (
                line,
                [line.name, dish_name(line.name)],
                f"line {line.id}: {line.quantity} x {dish_name(line.name)}",
            )
            for line in lines
        ],
        "line",
    )


@dataclass(frozen=True)
class _Choice:
    option_id: int
    name: str
    group: MenuOptionGroup
    meal_size: str | None  # None for the dish's own questions


def _choices(dish: MenuDish) -> list[_Choice]:
    found = [_Choice(o.id, o.name, g, None) for g in dish.option_groups for o in g.options]
    for meal in dish.meal_offers:
        for group in (meal.side, meal.drink):
            if group is not None:
                found += [_Choice(o.id, o.name, group, meal.size) for o in group.options]
    return found


def find_options(dish: MenuDish, names: Sequence[str], meal_size: str | None) -> list[int]:
    """The option id for each name, among the dish's own questions and, when `meal_size` is given,
    that meal's side and drink."""
    choices = _choices(dish)
    ids = []
    for name in names:
        usable = [c for c in choices if c.meal_size in (None, meal_size)]
        where = f" on {dish_name(dish.name)}"
        try:
            ids.append(
                _pick(name, [(c, [c.name], c.name) for c in usable], "option", where).option_id
            )
        except LookupFailed as problem:
            elsewhere = [c for c in choices if c not in usable]
            if problem.code == "unknown_option" and elsewhere:
                other = _pick_or_none(name, elsewhere)
                if other is not None:
                    raise _wrong_meal(name, other, meal_size) from problem
            raise
    return ids


def _pick_or_none(name: str, choices: Sequence[_Choice]) -> _Choice | None:
    try:
        return _pick(name, [(c, [c.name], c.name) for c in choices], "option")
    except LookupFailed:
        return None


def _wrong_meal(name: str, found: _Choice, meal_size: str | None) -> LookupFailed:
    size = found.meal_size
    if meal_size is None:
        return LookupFailed(
            "needs_meal_size",
            f"'{found.name}' is a choice of the {size} meal",
            f'Send meal_size "{size}" with it',
        )
    return LookupFailed(
        "wrong_meal_size",
        f"'{found.name}' is a choice of the {size} meal, not the {meal_size} meal",
        f'Send meal_size "{size}", or choose from the {meal_size} meal',
    )


def find_question(dish: MenuDish, name: str, meal_size: str | None) -> MenuOptionGroup:
    """The question a name stands for: one of the dish's own, or, when `meal_size` is given, the
    side or drink question of that meal."""
    every: list[tuple[MenuOptionGroup, str | None]] = [(g, None) for g in dish.option_groups]
    for meal in dish.meal_offers:
        every += [(g, meal.size) for g in (meal.side, meal.drink) if g is not None]
    usable = [g for g, size in every if size in (None, meal_size)]
    try:
        return _pick(
            name, [(g, [g.name], g.name) for g in usable], "question", f" on {dish_name(dish.name)}"
        )
    except LookupFailed as problem:
        if problem.code != "unknown_question":
            raise
        sizes = []
        for size in dict.fromkeys(size for _, size in every if size not in (None, meal_size)):
            others = [(g, [g.name], g.name) for g, s in every if s == size]
            try:
                _pick(name, others, "question")
                sizes.append(str(size))
            except LookupFailed:
                continue
        if not sizes:
            raise
        belongs = " or ".join(sizes)
        code = "needs_meal_size" if meal_size is None else "wrong_meal_size"
        raise LookupFailed(
            code,
            f"'{name}' is a question of the {belongs} meal",
            f'Send meal_size "{sizes[0]}"' + (f" (or {sizes[1]})" if len(sizes) > 1 else ""),
        ) from problem
