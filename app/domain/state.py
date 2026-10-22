"""State a chat holds: the clock, the order being filled and the customer, if known."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.backend.models import Customer, DriveThruOrder

Clock = Callable[[], datetime]

# The allergens the menu data lists, in the server's words (milk is dairy).
Allergen = Literal["milk", "gluten", "egg", "soy", "fish"]


@dataclass
class ActiveOrder:
    """The order this chat is filling: the ordering server's latest copy of it. Every tool that
    changes the order stores the server's reply here, so the chat can show the cart without a
    request. Empty until the first dish is added."""

    latest: DriveThruOrder | None = None

    @property
    def order_id(self) -> int | None:
        return self.latest.id if self.latest else None

    @property
    def placed(self) -> bool:
        return self.latest is not None and self.latest.status == "confirmed"


@dataclass
class Needs:
    """What the customer has said they cannot or will not eat. It lasts the whole chat and is
    shown to the model every turn, so it is never lost when older turns drop out of view."""

    allergies: list[str] = field(default_factory=list)
    veg_only: bool = False

    def add(self, allergies: Iterable[str], veg_only: bool) -> None:
        """Only ever adds: a need is not forgotten because the customer stopped mentioning it."""
        self.allergies += [a for a in allergies if a not in self.allergies]
        self.veg_only = self.veg_only or veg_only


@dataclass
class Caller:
    """Who is ordering. Nobody until they give a phone number: ordering never needs it."""

    customer: Customer | None = None
    usual: list[str] = field(default_factory=list)  # the dishes they order most, by name
    needs: Needs = field(default_factory=Needs)  # what they said this chat, kept all chat

    @property
    def allergies(self) -> list[str]:
        """The allergies on file: `preferences["allergies"]`, a list of words such as "milk"."""
        if self.customer is None:
            return []
        saved = self.customer.preferences.get("allergies", [])
        return [saved] if isinstance(saved, str) else [str(a) for a in saved]

    @property
    def avoid(self) -> list[str]:
        """Every allergy to keep in mind: the ones on file and the ones said this chat."""
        return [*self.allergies, *(a for a in self.needs.allergies if a not in self.allergies)]
