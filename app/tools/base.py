"""Tool base class and the context tools run in."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel

from app.backend.client import BackendClient
from app.domain.results import ToolResult
from app.domain.state import Clock, LedgerAction, LedgerEntry, WorkingState


class NotPermitted(Exception):
    """The acting customer does not own the entity, or it does not exist."""


@dataclass(frozen=True)
class ToolContext:
    """Built by the Session. The model never sees it."""

    backend: BackendClient
    customer_id: int | None
    clock: Clock

    def require_customer(self) -> int:
        """The bound customer id; the model never supplies it."""
        if self.customer_id is None:
            raise NotPermitted("No customer is identified")
        return self.customer_id

    def ledger(
        self,
        tool: str,
        action: LedgerAction,
        entity_id: int,
        summary: str,
        state: WorkingState | None = None,
    ) -> LedgerEntry:
        """A ledger entry stamped with the injected clock."""
        return LedgerEntry(
            tool=tool,
            action=action,
            entity_id=entity_id,
            summary=summary,
            timestamp=self.clock(),
            state=state,
        )


class Tool[A: BaseModel](ABC):
    """One file per tool. `description` says when to use it, not which endpoint it wraps."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    mutating: ClassVar[bool] = False
    destructive: ClassVar[bool] = False

    @abstractmethod
    def run(self, ctx: ToolContext, args: A) -> ToolResult:
        """Execute with validated arguments."""
