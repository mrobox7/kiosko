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


def test_discover_finds_the_order_tools_and_specs() -> None:
    reg = ToolRegistry.discover()
    names = {s.name for s in reg.specs()}  # tools defined by other tests can show up too
    assert {"get_menu", "get_item", "add_to_order", "remove_from_order", "place_order"} <= names
    spec = next(s for s in reg.specs() if s.name == "get_menu")
    assert {"category", "veg", "max_price", "sort"} <= set(spec.parameters["properties"])


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


def test_specs_drop_pydantic_noise_but_keep_meaning() -> None:
    specs = {s.name: s.parameters for s in ToolRegistry.discover().specs()}
    assert all('"title"' not in json.dumps(p) for p in specs.values())
    assert all("Arguments of" not in json.dumps(p) for p in specs.values())
    menu = specs["get_menu"]
    assert menu["properties"]["category"]["enum"] == [
        "burgers", "wraps", "fries-sides", "meals", "mccaf", "beverages", "desserts", "condiments"
    ]  # fmt: skip
    order = specs["add_to_order"]
    assert order["properties"]["quantity"]["maximum"] == 20
    assert order["$defs"]["OptionPick"]["properties"]["qty"]["maximum"] == 10


def test_optional_fields_lose_their_null_option_and_default_but_stay_optional() -> None:
    specs = {s.name: s.parameters for s in ToolRegistry.discover().specs()}
    menu = specs["get_menu"]
    text = json.dumps(specs)
    assert '"type": "null"' not in text and '"default": null' not in text
    assert menu["properties"]["max_price"] == {"type": "number"}  # lower bounds are not shown
    assert not any(k in text for k in ("maxLength", "minLength", '"minimum"', "exclusiveMinimum"))
    assert "required" not in menu  # every get_menu argument is still optional
    assert menu["properties"]["page"]["default"] == 1  # real defaults are kept


def test_trimmed_schemas_still_accept_what_the_model_may_send() -> None:
    reg = ToolRegistry.discover()
    ctx = make_ctx()
    # explicit nulls and omitted fields both still validate: only the wording was trimmed
    assert reg.dispatch("get_menu", {"category": None, "max_price": None}, ctx).ok
    assert reg.dispatch("get_menu", {}, ctx).ok


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
