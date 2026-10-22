"""note_need: allergies and diet kept for the whole order."""

import pytest

from app.backend.errors import BackendUnavailable
from tests.support.builders import make_order_tools

PHONE = {"phone": "98765 43210", "digits_confirmed": True}


def test_a_need_is_kept_on_the_chat_without_any_request() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("note_need", {"allergies": ["milk"]}, ctx)
    assert result.ok and result.data == {"allergies": ["milk"], "veg_only": False}
    assert ctx.caller.needs.allergies == ["milk"] and server.requests == []


def test_needs_add_up_and_nothing_is_repeated() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("note_need", {"allergies": ["milk", "egg"]}, ctx)
    result = tools.dispatch("note_need", {"allergies": ["egg", "soy"], "veg_only": True}, ctx)
    assert result.data == {"allergies": ["milk", "egg", "soy"], "veg_only": True}
    again = tools.dispatch("note_need", {"allergies": ["milk"]}, ctx)
    assert again.data["veg_only"] is True  # it only adds: a later call cannot take it back


@pytest.mark.parametrize(
    "args", [{}, {"allergies": []}, {"veg_only": False}, {"allergies": ["peanut"]}]
)
def test_nothing_to_note_or_an_unknown_allergen_is_refused(args: dict[str, object]) -> None:
    ctx, _, tools = make_order_tools()
    result = tools.dispatch("note_need", args, ctx)
    assert not result.ok and result.error is not None and result.error.code == "invalid_arguments"
    assert ctx.caller.needs.allergies == [] and not ctx.caller.needs.veg_only


def test_an_identified_customer_has_it_saved_with_what_was_already_on_file() -> None:
    ctx, server, tools = make_order_tools()
    server.preferences["allergies"] = ["fish"]
    tools.dispatch("set_customer", PHONE, ctx)
    result = tools.dispatch("note_need", {"allergies": ["milk"]}, ctx)
    assert result.ok and result.data["saved_to_record"] is True
    assert server.preferences["allergies"] == ["fish", "milk"]
    assert ("PATCH", "/customers/3/preferences") in server.requests
    assert ctx.caller.allergies == ["fish", "milk"]  # the held record is the server's copy


def test_if_saving_fails_the_need_still_holds_for_this_chat(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ctx, _, tools = make_order_tools()
    tools.dispatch("set_customer", PHONE, ctx)

    def down(*_: object) -> None:
        raise BackendUnavailable("down", may_have_been_processed=False)

    monkeypatch.setattr(ctx.backend, "patch_preferences", down)
    result = tools.dispatch("note_need", {"allergies": ["gluten"]}, ctx)
    assert result.ok and result.data["saved_to_record"] is False
    assert ctx.caller.needs.allergies == ["gluten"]


def test_the_summary_line_names_what_was_noted() -> None:
    ctx, _, tools = make_order_tools()
    args = {"allergies": ["milk"], "veg_only": True}
    done = tools.dispatch("note_need", args, ctx)
    assert tools.compact("note_need", args, done) == "noted: milk, veg only"
