"""The item list: the one typed contract between the supervisor's nodes.

The model writes `Draft`s and `Edit`s (words only). Code turns them into `Item`s and is the only
thing that sets `dish_id`, `option_ids` and `status`."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.backend.models import Allergen

Kind = Literal[
    "add",
    "remove",
    "change_qty",
    "place",
    "cancel",
    "phone",
    "need",
    "show_order",
    "search",
    "chat",
]
Status = Literal["ready", "needs_search", "needs_user", "done", "failed"]

ORDER_KINDS: tuple[Kind, ...] = (
    "add",
    "remove",
    "change_qty",
)  # lines the customer may still owe an answer on
# What a failed item's `result` says when the cause is one of these. They are codes for the code
# that writes the turn report, never words for a customer.
LOOKUP_DOWN = "lookup_unavailable"  # the menu lookup could not be run
HELD = "held_back"  # a place or cancel that waits for the open questions

OPEN: tuple[Status, ...] = ("needs_user",)  # the only status kept between turns: a question


class Draft(BaseModel):
    """One thing the customer asked for, in their words."""

    kind: Kind
    dish_text: str | None = None
    qty: int = Field(default=1, ge=1, le=20)
    options: list[str] = Field(default_factory=list)
    meal_size: Literal["Medium", "Large"] | None = None
    note: str | None = None
    target_line: int | None = None  # an order line id, for remove and change_qty
    phone: str | None = None  # the digits as said, for phone
    digits_confirmed: bool = False  # true only after the digits were read back and confirmed
    allergies: list[Allergen] = Field(default_factory=list)  # for need
    veg_only: bool = False  # for need


class Edit(BaseModel):
    """A change to an open item from an earlier turn, such as the answer to its question."""

    id: str
    dish_text: str | None = None
    qty: int | None = Field(default=None, ge=1, le=20)
    options: list[str] | None = None
    meal_size: Literal["Medium", "Large"] | None = None
    note: str | None = None
    phone: str | None = None
    digits_confirmed: bool | None = None
    drop: bool = False


class Understanding(BaseModel):
    """What the supervisor's first call returns."""

    language: Literal["en", "hi", "hinglish"] = "en"
    items: list[Draft] = Field(default_factory=list)
    updates: list[Edit] = Field(default_factory=list)
    reply: str | None = None  # only for a turn that is all chat


class Item(Draft):
    """A thing asked for, with what code has found out about it."""

    id: str
    status: Status = "needs_search"
    dish_id: int | None = None
    option_ids: list[int] = Field(default_factory=list)
    question: str | None = None  # set when the customer must choose
    candidates: list[str] = Field(default_factory=list)
    result: Any = None  # set when done or failed; a search answer lives here
