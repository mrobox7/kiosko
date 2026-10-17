from typing import Any

from pydantic import BaseModel

from app.backend.errors import BackendRuleViolation, BackendUnavailable
from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.registry import ToolRegistry
from tests.support.fake_backend import FakeBackend


class Args(BaseModel):
    n: int


class Boom(Tool[Args]):
    name = "boom"
    description = "test"
    args_model = Args
    kind: Any = None

    def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        raise self.kind


def setup(kind: Exception | None = None) -> tuple[ToolRegistry, ToolContext]:
    tool = Boom()
    tool.kind = kind
    fake = FakeBackend()
    return ToolRegistry([tool]), ToolContext(backend=fake.client)


def code(result: ToolResult) -> str | None:
    return result.error.code if result.error else None


def test_discover_finds_list_menu_and_specs() -> None:
    reg = ToolRegistry.discover()
    spec = next(s for s in reg.specs() if s.name == "list_menu")
    assert "exclude_tags" in spec.parameters["properties"]


def test_unknown_tool_lists_available() -> None:
    reg, ctx = setup()
    r = reg.dispatch("nope", {}, ctx)
    assert code(r) == "unknown_tool" and r.error and "boom" in (r.error.hint or "")


def test_parse_error_never_reaches_tool() -> None:
    reg, ctx = setup(RuntimeError("must not run"))
    assert code(reg.dispatch("boom", {}, ctx, parse_error="bad json")) == "malformed_arguments_json"


def test_invalid_arguments_name_fields() -> None:
    reg, ctx = setup(RuntimeError("must not run"))
    r = reg.dispatch("boom", {"n": "x"}, ctx)
    assert code(r) == "invalid_arguments" and r.error and "n" in (r.error.hint or "")


def test_backend_errors_mapped() -> None:
    reg, ctx = setup(BackendRuleViolation("Slot taken"))
    r = reg.dispatch("boom", {"n": 1}, ctx)
    assert code(r) == "backend_rejected" and r.error and r.error.message == "Slot taken"
    reg, ctx = setup(BackendUnavailable("down"))
    assert code(reg.dispatch("boom", {"n": 1}, ctx)) == "backend_unavailable"


def test_unexpected_exception_becomes_internal_error() -> None:
    reg, ctx = setup(ValueError("secret detail"))
    r = reg.dispatch("boom", {"n": 1}, ctx)
    assert code(r) == "internal_error" and "secret" not in r.model_dump_json()


def test_list_menu_filters_and_trims() -> None:
    reg = ToolRegistry.discover()
    ctx = ToolContext(backend=FakeBackend().client)
    r = reg.dispatch(
        "list_menu", {"category": "starter", "tags_any": ["vegetarian"], "max_price": 400}, ctx
    )
    assert r.ok
    items = r.data["items"]
    assert items and set(items[0]) == {"id", "name", "price", "category", "tags", "available"}
    assert all(i["price"] <= 400 for i in items)


def test_list_menu_rejects_unknown_tag() -> None:
    reg = ToolRegistry.discover()
    ctx = ToolContext(backend=FakeBackend().client)
    assert code(reg.dispatch("list_menu", {"exclude_tags": ["gluten"]}, ctx)) == "invalid_arguments"


def test_list_menu_rejects_wrong_category_case() -> None:
    reg = ToolRegistry.discover()
    ctx = ToolContext(backend=FakeBackend().client)
    assert code(reg.dispatch("list_menu", {"category": "Starters"}, ctx)) == "invalid_arguments"
