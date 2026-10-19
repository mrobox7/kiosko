"""Tool discovery and safe dispatch."""

import importlib
import inspect
import logging
import pkgutil
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

import app.tools as tools_package
from app.backend.errors import BackendError, BackendUnavailable
from app.domain.messages import ToolSpec
from app.domain.results import (
    BACKEND_REJECTED,
    BACKEND_UNAVAILABLE,
    INTERNAL_ERROR,
    INVALID_ARGUMENTS,
    MALFORMED_ARGUMENTS_JSON,
    NOT_PERMITTED,
    UNKNOWN_TOOL,
    ToolResult,
)
from app.tools.base import NotPermitted, Tool, ToolContext

logger = logging.getLogger(__name__)


_NULL = {"type": "null"}


def _without_null_option(schema: dict[str, Any]) -> dict[str, Any]:
    """`anyOf: [X, null]` is how pydantic writes an optional field. Being absent from
    `required` already says so, so keep just X."""
    options = schema.get("anyOf")
    if isinstance(options, list) and len(options) == 2:
        real = [o for o in options if o != _NULL]
        if len(real) == 1 and isinstance(real[0], dict):
            rest = {k: v for k, v in schema.items() if k != "anyOf"}
            return {**real[0], **rest}
    return schema


def _compact_schema(schema: Any, *, top: bool = True) -> Any:
    """Drop what pydantic adds that the model does not need: `title` keywords, the class
    docstring on the top-level schema (the tool description already says it), `default: null`
    and the null option of optional fields."""
    if isinstance(schema, list):
        return [_compact_schema(item, top=False) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in _without_null_option(schema).items():
        if key == "title" and isinstance(value, str):
            continue
        if key == "description" and top:
            continue
        if key == "default" and value is None:
            continue
        if key in ("properties", "$defs"):  # keys here are names, not keywords
            out[key] = {k: _compact_schema(v, top=False) for k, v in value.items()}
        else:
            out[key] = _compact_schema(value, top=False)
    return out


class ToolRegistry:
    """Holds the tools, exposes their specs, and dispatches calls without ever raising."""

    def __init__(self, tools: Iterable[Tool[Any]]) -> None:
        self._tools = {t.name: t for t in tools}

    @classmethod
    def discover(cls) -> ToolRegistry:
        """Instantiate every concrete Tool subclass found in the tools package."""
        for module in pkgutil.iter_modules(tools_package.__path__):
            importlib.import_module(f"{tools_package.__name__}.{module.name}")
        found = [t for t in _all_subclasses(Tool) if not inspect.isabstract(t)]
        return cls(t() for t in found)

    def specs(self) -> list[ToolSpec]:
        """Specs sent to the model, in a stable order."""
        return [
            ToolSpec(
                name=t.name,
                description=t.description,
                parameters=_compact_schema(t.args_model.model_json_schema()),
            )
            for t in sorted(self._tools.values(), key=lambda t: t.name)
        ]

    def compact(self, name: str, raw_args: dict[str, Any], result: ToolResult) -> str:
        """The tool's one-line form of a call. Never raises: a broken or missing compactor, or
        arguments that no longer validate, degrade to ok / error, because the summary must
        not break a turn."""
        tool = self._tools.get(name)
        try:
            if tool is not None:
                return tool.compact(result, tool.args_model.model_validate(raw_args))
        except Exception:  # boundary: tools must never raise into the loop
            logger.exception("Tool %s failed to compact its result", name)
        return f"error: {result.error.code}" if result.error else ("ok" if result.ok else "error")

    def dispatch(
        self,
        name: str,
        raw_args: dict[str, Any],
        ctx: ToolContext,
        parse_error: str | None = None,
    ) -> ToolResult:
        """Run a tool call. Every failure becomes an error ToolResult."""
        if parse_error:
            return ToolResult.failure(
                MALFORMED_ARGUMENTS_JSON, parse_error, "Resend the call with valid JSON arguments."
            )
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
            return tool.run(ctx, args)
        except NotPermitted:
            return ToolResult.failure(
                NOT_PERMITTED,
                "That reservation or order is not on this customer's account.",
                "Do not retry with other ids. Offer to list the customer's own bookings.",
            )
        except BackendUnavailable as exc:
            return ToolResult.failure(
                BACKEND_UNAVAILABLE,
                exc.message,
                "Tell the customer the system is unavailable; do not retry in a loop.",
            )
        except BackendError as exc:
            return ToolResult.failure(BACKEND_REJECTED, exc.message)
        except Exception:  # boundary: tools must never raise into the loop
            logger.exception("Tool %s crashed", name)
            return ToolResult.failure(
                INTERNAL_ERROR, "The tool failed unexpectedly.", "Apologise and offer to try again."
            )


def _all_subclasses(cls: type) -> list[type[Tool[Any]]]:
    out: list[type[Tool[Any]]] = []
    for sub in cls.__subclasses__():  # type: ignore[var-annotated]
        out.append(sub)
        out.extend(_all_subclasses(sub))
    return out
