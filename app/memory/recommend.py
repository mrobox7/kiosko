"""Picking dishes to suggest. Pure code: the model only words the answer."""

from collections import Counter, defaultdict
from collections.abc import Sequence

from app.backend.models import MenuItem
from app.memory.profile import OrderLine

SUGGESTIONS = 3


def rank(menu: Sequence[MenuItem], history: Sequence[OrderLine]) -> list[tuple[MenuItem, str]]:
    """Up to SUGGESTIONS (dish, reason) pairs from an already-filtered menu.

    Dishes the customer ordered before come first, most ordered first. The rest are new dishes,
    taken from each category in turn so the suggestions are not three starters."""
    totals: Counter[str] = Counter()
    for line in history:
        totals[line.item] += line.quantity
    known = sorted((i for i in menu if i.name in totals), key=lambda i: (-totals[i.name], i.id))
    by_category: dict[str, list[MenuItem]] = defaultdict(list)
    for item in menu:
        if item.name not in totals:
            by_category[item.category].append(item)
    sections = list(by_category)  # menu order: starters, mains, desserts
    fresh = sorted(
        (item for items in by_category.values() for item in items),
        key=lambda i: (by_category[i.category].index(i), sections.index(i.category)),
    )
    picked = [(i, f"ordered {totals[i.name]}x before") for i in known]
    picked += [(i, "new to you") for i in fresh]
    return picked[:SUGGESTIONS]
