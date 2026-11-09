"""How a question of a dish reads to the model: its name, whether it must be answered, how many
may be picked, and its options (or only how many there are when they were not asked for)."""

from typing import Any

from app.backend.models import Option, OptionGroup
from app.menu.names import option_name

INLINE = 8  # a question with more options than this shows a count until it is opened


def options_of(group: OptionGroup, options: list[Option] | None = None) -> list[str]:
    return [
        option_name(o.name)
        if not o.price_delta
        else f"{option_name(o.name)} ({'+' if o.price_delta > 0 else '-'}₹{abs(o.price_delta):g})"
        for o in (group.options if options is None else options)
    ]


def question_of(group: OptionGroup, options: list[str] | None) -> dict[str, Any]:
    if group.min_select == group.max_select:
        pick = str(group.max_select)
    elif group.min_select == 0:
        pick = f"up to {group.max_select}"
    else:
        pick = f"{group.min_select}-{group.max_select}"
    data: dict[str, Any] = {
        "question": group.name,
        "required": group.min_select >= 1,
        "pick": pick,
    }
    if options is None:
        data["options_count"] = len(group.options)
    else:
        data["options"] = options
    return data


def overview_of(group: OptionGroup) -> dict[str, Any]:
    """The question with its options when there are few, else with their number."""
    return question_of(group, options_of(group) if len(group.options) <= INLINE else None)
