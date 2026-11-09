"""The menu card: what the supervisor's models are told about the menu. It names the sections,
which diets each serves and up to a few dishes of each as examples. Dish names are matched in code
(see fuzzy.py), so the model does not need the whole list, and a model shown a partial list tends
to say a dish that is not on it is not sold: each partial list says how many more there are."""

from collections.abc import Sequence

from app.backend.models import Category, Dish
from app.menu.names import dish_name

SHOWN = 5  # dishes named per section


def _diet(dishes: Sequence[Dish]) -> str:
    kinds = {d.veg for d in dishes}
    if kinds == {"veg"}:
        return "veg"
    if kinds == {"non_veg"}:
        return "non-veg"
    return "veg + non-veg"


def _names(dishes: Sequence[Dish]) -> list[str]:
    """Each dish's name once, bestsellers first, then in menu order."""
    ranked = sorted(dishes, key=lambda d: "bestseller" not in d.tags)  # stable
    return list(dict.fromkeys(dish_name(d.name) for d in ranked))


def render_card(categories: Sequence[Category], dishes: Sequence[Dish]) -> str:
    """One line per section: its name, the slug the menu tools take, its diets, and up to SHOWN of
    its dishes, with how many more there are. A section the dishes use but the menu does not name
    is still shown, under its slug, so no dish is ever missing from the card."""
    named = {c.slug: c.name for c in categories}
    slugs = list(dict.fromkeys([*named, *(d.category for d in dishes)]))
    lines = []
    for slug in slugs:
        here = [d for d in dishes if d.category == slug]
        if not here:
            continue
        names = _names(here)
        more = f" (+{len(names) - SHOWN} more)" if len(names) > SHOWN else ""
        title = named.get(slug) or slug.replace("-", " ").title()
        lines.append(f"{title} [{slug}]: {_diet(here)} - {', '.join(names[:SHOWN])}{more}")
    return "\n".join(lines)
