"""Describing a tool to the model: its name, what it is for, and its arguments as a JSON schema."""

from typing import Any

from app.llm.messages import ToolSpec


def schema_of(schema: dict[str, Any]) -> dict[str, Any]:
    """A pydantic JSON schema in the plainest form for a provider: references inlined, titles and
    the `$defs` block dropped."""
    defs: dict[str, Any] = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
        return {
            k: ({n: walk(v) for n, v in val.items()} if k == "properties" else walk(val))
            for k, val in node.items()
            if k not in ("$defs", "title")
        }

    plain: dict[str, Any] = walk(schema)
    return plain


def spec_of(name: str, description: str, schema: dict[str, Any]) -> ToolSpec:
    return ToolSpec(name=name, description=description, parameters=schema_of(schema))
