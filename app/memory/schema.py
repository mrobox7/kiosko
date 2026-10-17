"""Stored preferences: vocabularies, tolerant reading, and the merge rule.

The backend keeps preferences as a free-form blob that the customer's own words end up in,
so everything read from it is checked against these vocabularies before the model sees it."""

from collections.abc import Sequence
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

Seating = Literal["indoor", "outdoor"]
Dietary = Literal["vegetarian", "vegan"]
Allergen = Literal["nuts", "dairy", "gluten", "shellfish", "egg", "soy"]

SCHEMA_VERSION = 1
SEATING_VALUES: tuple[str, ...] = get_args(Seating)
DIETARY_VALUES: tuple[str, ...] = get_args(Dietary)
ALLERGEN_VALUES: tuple[str, ...] = get_args(Allergen)
# Only these allergens can be checked against menu tags; the rest need a human.
ALLERGEN_MENU_TAG: dict[str, str] = {"nuts": "contains-nuts", "dairy": "contains-dairy"}


def _norm(value: Any) -> str | None:
    return value.strip().lower() if isinstance(value, str) else None


def _known(values: Any, allowed: tuple[str, ...]) -> list[str]:
    items = [values] if isinstance(values, str) else values if isinstance(values, list) else []
    out: list[str] = []
    for item in items:
        normed = _norm(item)
        if normed in allowed and normed not in out:
            out.append(normed)
    return out


class Preferences(BaseModel):
    """What we are willing to show the model: whitelisted fields and values only."""

    seating: Seating | None = None
    dietary: list[Dietary] = Field(default_factory=list)
    allergies: list[Allergen] = Field(default_factory=list)

    @classmethod
    def from_blob(cls, blob: dict[str, Any]) -> Preferences:
        """Read any blob the backend holds; unknown keys and values are ignored."""
        seating = _norm(blob.get("seating"))
        return cls.model_validate(
            {
                "seating": seating if seating in SEATING_VALUES else None,
                "dietary": _known(blob.get("dietary"), DIETARY_VALUES),
                "allergies": _known(blob.get("allergies"), ALLERGEN_VALUES),
            }
        )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value] if isinstance(value, str) else []


def _merge_list(existing: list[Any], add: Sequence[str], remove: Sequence[str]) -> list[Any]:
    """Keep every existing value (even ones we do not recognise) except the removed ones."""
    kept = [v for v in existing if _norm(v) not in set(remove)]
    present = {_norm(v) for v in kept}
    return kept + [a for a in dict.fromkeys(add) if a not in present]


def merge_preferences(
    blob: dict[str, Any],
    *,
    seating: str | None = None,
    dietary_add: Sequence[str] = (),
    dietary_remove: Sequence[str] = (),
    allergies_add: Sequence[str] = (),
    allergies_remove: Sequence[str] = (),
) -> tuple[dict[str, Any], bool]:
    """Apply explicit changes to the stored blob and return (new blob, changed).

    The backend merges shallowly, so list fields are read, merged and written back whole.
    Unknown keys, and unknown values inside the lists, are preserved."""
    out = dict(blob)
    if seating:
        out["seating"] = seating
    for key, add, remove in (
        ("dietary", dietary_add, dietary_remove),
        ("allergies", allergies_add, allergies_remove),
    ):
        current = _as_list(blob.get(key))
        merged = _merge_list(current, add, remove)
        if merged != current:
            out[key] = merged
    changed = out != blob
    if changed:
        out.setdefault("schema_version", SCHEMA_VERSION)
    return out, changed
