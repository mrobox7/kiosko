"""The menu outline: the part of the menu the model always has in front of it."""

from collections.abc import Sequence

from app.backend.models import MenuDish
from app.menu.names import dish_name


def render_outline(dishes: Sequence[MenuDish]) -> str:
    """One line per category, in menu order: `category: dish, dish, ...`. The category is the
    slug that get_menu takes. Names only: prices, choices and nutrition are for the tools."""
    lines: dict[str, list[str]] = {}
    for dish in dishes:
        names = lines.setdefault(dish.category, [])
        if (name := dish_name(dish.name)) and name not in names:
            names.append(name)
    return "\n".join(f"{category}: {', '.join(names)}" for category, names in lines.items())
