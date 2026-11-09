"""Tool discovery and safe dispatch."""

import importlib
import inspect
import logging
import pkgutil
from collections.abc import Iterable
from typing import Any, ClassVar

from pydantic import ValidationError

import app.tools as tools_package
from app.backend.errors import BackendError, BackendUnavailable
from app.tools.backend_errors import refusal_for
from app.tools.contract import (
    BACKEND_REJECTED,
    BACKEND_UNAVAILABLE,
    INTERNAL_ERROR,
    INVALID_ARGUMENTS,
    UNKNOWN_TOOL,
    Tool,
    ToolAborted,
    ToolContext,
    ToolResult,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Holds the tools, exposes their specs, and dispatches calls without ever raising."""

    def __init__(self, tools: Iterable[Tool[Any]]) -> None:
        self._tools = {t.name: t for t in tools}

    _shared: ClassVar[ToolRegistry | None] = None

    @classmethod
    def discover(cls) -> ToolRegistry:
        """Instantiate every concrete Tool subclass found in the tools package and its folders."""
        for module in pkgutil.walk_packages(tools_package.__path__, f"{tools_package.__name__}."):
            importlib.import_module(module.name)
        found = [t for t in _all_subclasses(Tool) if not inspect.isabstract(t)]
        return cls(t() for t in found)

    @classmethod
    def shared(cls) -> ToolRegistry:
        """The one registry of this process. Discovering imports every tool module, so it is done
        once and the nodes share the result."""
        if cls._shared is None:
            cls._shared = cls.discover()
        return cls._shared

    def args_schema(self, name: str) -> dict[str, Any]:
        """The JSON schema of a tool's arguments, for describing the tool to the model."""
        return self._tools[name].args_model.model_json_schema()

    def dispatch(
        self,
        name: str,
        raw_args: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        """Run a tool call. Every failure becomes an error ToolResult."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.failure(
                UNKNOWN_TOOL,
                f"No tool named '{name}'.",
                f"Available tools: {', '.join(sorted(self._tools))}.",
            )
        try:
            args = tool.args_model.model_validate(raw_args)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) or "<root>" for e in exc.errors()})
            return ToolResult.failure(
                INVALID_ARGUMENTS,
                "Invalid arguments.",
                f"Fix these fields: {', '.join(fields)}.",
            )
        try:
            result = tool.run(ctx, args)
        except ToolAborted as aborted:
            result = self._failure(name, ctx, aborted.cause)
            result.update = aborted.update  # what the tool had already changed
        except Exception as exc:  # boundary: tools must never raise into the loop
            result = self._failure(name, ctx, exc)
        return result

    @staticmethod
    def _failure(name: str, ctx: ToolContext, exc: Exception) -> ToolResult:
        """The error result for an exception a tool raised."""
        if isinstance(exc, BackendUnavailable):
            return ToolResult.failure(
                BACKEND_UNAVAILABLE,
                exc.message,
                "Tell the customer the system is unavailable; do not retry in a loop.",
            )
        if isinstance(exc, BackendError):
            return refusal_for(ctx, exc) or ToolResult.failure(BACKEND_REJECTED, exc.message)
        logger.error("Tool %s crashed", name, exc_info=exc)
        return ToolResult.failure(
            INTERNAL_ERROR, "The tool failed unexpectedly.", "Apologise and offer to try again."
        )


def _all_subclasses(cls: type) -> list[type[Tool[Any]]]:
    """Every subclass of `cls`, however deep."""
    found: list[type[Tool[Any]]] = []
    for sub in cls.__subclasses__():  # type: ignore[var-annotated]
        found.append(sub)
        found.extend(_all_subclasses(sub))
    return found
