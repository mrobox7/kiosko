"""Scores how well the customer's words name each dish, in plain code, so that "mc aloo tikki" finds
"McAloo Tikki Burger" without a model. Spaces are ignored (spoken words split names differently
from the menu), and small spelling differences cost little."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from app.backend.models import Dish
from app.menu.names import dish_name, normalise

MIN_CHARS = 4  # a shorter text is not taken as part of a name
HIGH = 0.85  # sure enough to take the best dish without asking...
GAP = 0.10  # ...when the next best is at least this far behind
LOW = 0.6  # below this a dish is not worth suggesting
SHOWN = 3  # dishes put to the customer when unsure
COMBO_WORDS = {"meal", "combo"}  # combos count only when the customer said one of these


@dataclass(frozen=True)
class Match:
    score: float  # 0 to 1; 1 is the whole name
    dish: Dish


def _squash(text: str) -> str:
    return normalise(text).replace(" ", "")


def score(text: str, name: str) -> float:
    """How well `text` names `name`: 1 for the whole name, a little less for part of it, lower for
    a near spelling."""
    said, named = _squash(text), _squash(name)
    if not said or not named:
        return 0.0
    if said == named:
        return 1.0
    closeness = SequenceMatcher(None, said, named).ratio()
    if len(said) >= MIN_CHARS and said in named:  # part of the name: more of it, more sure
        return max(closeness, 0.75 + 0.25 * len(said) / len(named))
    return closeness


def rank(text: str, dishes: Sequence[Dish]) -> list[Match]:
    """Every dish that scores above zero, best first."""
    found = [Match(score(text, dish_name(d.name)), d) for d in dishes]
    return sorted((m for m in found if m.score > 0), key=lambda m: -m.score)


@dataclass(frozen=True)
class Verdict:
    """`match`: this dish. `ask`: the customer picks from `candidates`. `none`: nothing close."""

    kind: Literal["match", "ask", "none"]
    dish: Dish | None = None
    candidates: list[Dish] = field(default_factory=list)


def pick(text: str, dishes: Sequence[Dish]) -> Verdict:
    """The dish the customer's words name. A wrong dish on an order is worse than one more
    question, so a dish is taken only when it is the whole name or clearly ahead of the rest."""
    said = set(normalise(text).split())
    pool = dishes if said & COMBO_WORDS else [d for d in dishes if d.kind != "combo"]
    ranked = rank(text, pool)
    if not ranked:
        return Verdict("none")
    top, second = ranked[0].score, ranked[1].score if len(ranked) > 1 else 0.0
    if (top >= 1.0 and second < 1.0) or (top >= HIGH and top - second >= GAP):
        return Verdict("match", ranked[0].dish)
    near = [m.dish for m in ranked[:SHOWN] if m.score >= LOW]
    return Verdict("ask", candidates=near) if near else Verdict("none")
