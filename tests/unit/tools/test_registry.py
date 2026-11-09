from typing import Any

from pydantic import BaseModel

from app.backend.errors import BackendRuleViolation, BackendUnavailable
from app.tools.contract import Tool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx


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
    return ToolRegistry([tool]), make_ctx()


def code(result: ToolResult) -> str | None:
    return result.error.code if result.error else None


def test_unknown_tool_lists_available() -> None:
    reg, ctx = setup()
    r = reg.dispatch("nope", {}, ctx)
    assert code(r) == "unknown_tool" and r.error and "boom" in (r.error.hint or "")


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


def test_get_menu_filters_and_trims() -> None:
    reg = ToolRegistry.discover()
    r = reg.dispatch("get_menu", {"category": "burgers", "max_price": 100}, make_ctx())
    assert r.ok
    items = r.data["dishes"]
    assert items and set(items[0]) == {"dish_id", "name", "price", "veg", "combo"}
    assert all(i["price"] <= 100 for i in items)


def test_get_menu_rejects_an_unknown_kind() -> None:
    reg = ToolRegistry.discover()
    assert code(reg.dispatch("get_menu", {"kind": "bundle"}, make_ctx())) == "invalid_arguments"


def test_get_menu_rejects_wrong_category_case() -> None:
    reg = ToolRegistry.discover()
    assert (
        code(reg.dispatch("get_menu", {"category": "Burgers"}, make_ctx())) == "invalid_arguments"
    )


def test_trimmed_schemas_still_accept_what_the_model_may_send() -> None:
    reg = ToolRegistry.discover()
    ctx = make_ctx()
    # explicit nulls and omitted fields both still validate: only the wording was trimmed
    assert reg.dispatch("get_menu", {"category": None, "max_price": None}, ctx).ok
    assert reg.dispatch("get_menu", {}, ctx).ok
