"""Tool base class and the context tools run in."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel

from app.backend.client import BackendClient
from app.domain.results import ToolResult


@dataclass(frozen=True)
class ToolContext:
    """Built by the Session. The model never sees it."""

    backend: BackendClient


class Tool[A: BaseModel](ABC):
    """One file per tool. `description` says when to use it, not which endpoint it wraps."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    mutating: ClassVar[bool] = False

    @abstractmethod
    def run(self, ctx: ToolContext, args: A) -> ToolResult:
        """Execute with validated arguments."""
