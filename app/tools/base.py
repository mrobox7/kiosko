"""Tool base class and the context tools run in."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import BaseModel

from app.backend.client import BackendClient
from app.domain.results import ToolResult
from app.domain.state import ActiveOrder, Caller, Clock
from app.menu.menu import Menu


@dataclass(frozen=True)
class ToolContext:
    """Built by the Session. The model never sees it."""

    backend: BackendClient
    clock: Clock
    outlet_code: str = ""
    order: ActiveOrder = field(default_factory=ActiveOrder)
    caller: Caller = field(default_factory=Caller)
    menu: Menu = field(kw_only=True)  # the whole menu, for names, ids, choices and filters

    @property
    def customer_id(self) -> int | None:
        """The customer, once they have given a phone number."""
        return self.caller.customer.id if self.caller.customer else None


class Tool[A: BaseModel](ABC):
    """One file per tool. `description` says when to use it, not which endpoint it wraps."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    mutating: ClassVar[bool] = False
    destructive: ClassVar[bool] = False
    shown_in_order: ClassVar[bool] = False  # a success shows in the order the context carries

    @abstractmethod
    def run(self, ctx: ToolContext, args: A) -> ToolResult:
        """Execute with validated arguments."""

    def compact(self, result: ToolResult, args: A) -> str:
        """One line for the turn summary, built from the result and the call's arguments.
        The default is ok / the error code; override where later turns need ids or values."""
        if result.ok:
            return "ok"
        return f"error: {result.error.code}" if result.error else "error"
