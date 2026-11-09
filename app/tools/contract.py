"""What a tool is, what it is given and what it hands back.

A tool is a class with typed arguments and a `run` (`Tool`). It reads the chat through a
`ToolContext` and never changes it: what it changes it returns in an `Update`, inside a
`ToolResult`, and the caller applies it."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.backend.client import BackendClient
from app.backend.models import Customer, Order
from app.menu.menu import Menu

# Error codes a tool result can carry.
UNKNOWN_TOOL = "unknown_tool"
INVALID_ARGUMENTS = "invalid_arguments"
BACKEND_REJECTED = "backend_rejected"
BACKEND_UNAVAILABLE = "backend_unavailable"
INTERNAL_ERROR = "internal_error"


class ToolError(BaseModel):
    """Error code plus a message and an optional hint the model can act on."""

    code: str
    message: str
    hint: str | None = None


class Update(BaseModel):
    """What a tool changed in the chat's state. A tool never changes what it was given: it returns
    this, and the caller applies it."""

    order: Order | None = None  # the order's new latest copy
    clear_order: bool = False  # the order is gone: the next dish starts a new one
    customer: Customer | None = None
    usual: list[str] | None = None  # the customer's usual dishes
    allergies: list[str] = Field(default_factory=list)  # added to the chat's needs
    veg_only: bool = False  # added to the chat's needs


class ToolAborted(Exception):
    """A tool failed with `cause` after it had already changed something, which `update` records."""

    def __init__(self, cause: Exception, update: Update) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.update = update


class ToolResult(BaseModel):
    """What a tool hands back to the loop: data on success, an error otherwise."""

    ok: bool
    data: Any = None
    error: ToolError | None = None
    changed: bool = False  # the call changed the order; never shown to the model
    update: Update | None = None  # the changes to the chat's state; never shown to the model

    @classmethod
    def success(cls, data: Any) -> ToolResult:
        """A successful result."""
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: str, message: str, hint: str | None = None) -> ToolResult:
        """A failed result."""
        return cls(ok=False, error=ToolError(code=code, message=message, hint=hint))


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ToolContext:
    """What a tool may read about the chat, as plain values, and the means to reach the ordering
    server. Tools change none of it: what they change they return in an `Update`, and the caller
    makes the next context with `after`. The model never sees it."""

    backend: BackendClient
    clock: Clock
    outlet_code: str = ""
    menu: Menu = field(kw_only=True)  # the whole menu, for names, ids, choices and filters
    order: Order | None = None  # the ordering server's latest copy; None until a dish
    customer: Customer | None = None  # nobody until they give a phone number
    usual: tuple[str, ...] = ()  # the dishes the customer orders most, by name
    allergies: tuple[str, ...] = ()  # said this chat; only ever added to
    veg_only: bool = False  # said this chat; once set it stays

    @property
    def customer_id(self) -> int | None:
        """The customer, once they have given a phone number."""
        return self.customer.id if self.customer else None

    @property
    def placed(self) -> bool:
        return self.order is not None and self.order.status == "confirmed"

    def after(self, update: Update | None) -> ToolContext:
        """The context once `update` has happened."""
        if update is None:
            return self
        order = None if update.clear_order else (update.order or self.order)
        return replace(
            self,
            order=order,
            customer=update.customer or self.customer,
            usual=tuple(self.usual if update.usual is None else update.usual),
            allergies=(*self.allergies, *(a for a in update.allergies if a not in self.allergies)),
            veg_only=self.veg_only or update.veg_only,
        )


class Tool[A: BaseModel](ABC):
    """One file per tool: the arguments it takes and what it does with them."""

    name: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def run(self, ctx: ToolContext, args: A) -> ToolResult:
        """Execute with validated arguments."""


def exactly_one(a: object, b: object, names: str) -> None:
    """For argument models: a dish or option is named or numbered, never both and never neither."""
    if (a is None) == (b is None):
        raise ValueError(f"send one of {names}, not both and not neither")
