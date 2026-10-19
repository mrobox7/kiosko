import json
from typing import Any

from pydantic import BaseModel

from app.backend.errors import BackendRuleViolation, BackendUnavailable
from app.domain.results import ToolResult
from app.tools.base import Tool, ToolContext
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
    ctx = make_ctx()
    r = reg.dispatch(
        "list_menu", {"category": "starter", "tags_any": ["vegetarian"], "max_price": 400}, ctx
    )
    assert r.ok
    items = r.data["items"]
    assert items and set(items[0]) == {"id", "name", "price", "category", "tags", "available"}
    assert all(i["price"] <= 400 for i in items)


def test_list_menu_rejects_unknown_tag() -> None:
    reg = ToolRegistry.discover()
    ctx = make_ctx()
    assert code(reg.dispatch("list_menu", {"exclude_tags": ["gluten"]}, ctx)) == "invalid_arguments"


def test_list_menu_rejects_wrong_category_case() -> None:
    reg = ToolRegistry.discover()
    ctx = make_ctx()
    assert code(reg.dispatch("list_menu", {"category": "Starters"}, ctx)) == "invalid_arguments"


def test_specs_drop_pydantic_noise_but_keep_meaning() -> None:
    specs = {s.name: s.parameters for s in ToolRegistry.discover().specs()}
    assert all('"title"' not in json.dumps(p) for p in specs.values())
    assert all("Arguments of" not in json.dumps(p) for p in specs.values())
    menu = specs["list_menu"]
    assert menu["properties"]["max_price"]["description"] == "Maximum price per item"
    assert menu["properties"]["category"]["enum"] == ["starter", "main", "dessert"]
    order = specs["add_order_items"]
    assert order["required"] == ["reservation_id", "items"]
    assert order["$defs"]["OrderItem"]["required"] == ["menu_item_id"]
    assert order["properties"]["items"]["maxItems"] == 10


def test_optional_fields_lose_their_null_option_and_default_but_stay_optional() -> None:
    specs = {s.name: s.parameters for s in ToolRegistry.discover().specs()}
    menu = specs["list_menu"]
    text = json.dumps(specs)
    assert '"type": "null"' not in text and '"default": null' not in text
    assert menu["properties"]["max_price"] == {
        "type": "number",
        "description": "Maximum price per item",
    }
    assert "required" not in menu  # every list_menu argument is still optional
    assert menu["properties"]["available_only"]["default"] is True  # real defaults are kept


def test_trimmed_schemas_still_accept_what_the_model_may_send() -> None:
    reg = ToolRegistry.discover()
    ctx = make_ctx()
    # explicit nulls and omitted fields both still validate: only the wording was trimmed
    assert reg.dispatch("list_menu", {"category": None, "max_price": None}, ctx).ok
    assert reg.dispatch("list_menu", {}, ctx).ok


def test_a_property_named_default_survives() -> None:
    class Args(BaseModel):
        default: str | None = None

    class Defaulted(Tool[Args]):
        name = "defaulted"
        description = "d"
        args_model = Args

        def run(self, ctx: ToolContext, args: Args) -> ToolResult:
            return ToolResult.success(None)

    assert "default" in ToolRegistry([Defaulted()]).specs()[0].parameters["properties"]


def test_a_property_named_title_survives() -> None:
    class Args(BaseModel):
        title: str

    class Titled(Tool[Args]):
        name = "titled"
        description = "t"
        args_model = Args

        def run(self, ctx: ToolContext, args: Args) -> ToolResult:
            return ToolResult.success(None)

    schema = ToolRegistry([Titled()]).specs()[0].parameters
    assert "title" in schema["properties"] and schema["required"] == ["title"]
