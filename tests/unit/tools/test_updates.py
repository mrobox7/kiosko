"""Tools change nothing they were given: they return what changed, and the caller makes the next
context from it."""

import dataclasses

from app.tools.customer.note_need import NoteNeed, NoteNeedArgs
from app.tools.customer.set_customer import SetCustomer, SetCustomerArgs
from app.tools.order.add_to_order import AddToOrder, AddToOrderArgs
from app.tools.order.cancel_order import CancelOrder, CancelOrderArgs
from tests.support.builders import make_order_tools

PHONE = "98765 43210"


def test_add_to_order_returns_the_new_order_and_leaves_the_context_alone() -> None:
    chat, _, _ = make_order_tools()
    result = AddToOrder().run(chat.ctx, AddToOrderArgs(dish_id=4, options=[{"option_id": 1}]))
    assert result.ok and result.update is not None and result.update.order is not None
    assert [i.name for i in result.update.order.lines] == ["McAloo Tikki"]
    assert chat.ctx.order is None  # the tool changed nothing it was given


def test_a_refused_first_dish_still_returns_the_draft_it_started() -> None:
    chat, server, _ = make_order_tools()
    result = AddToOrder().run(chat.ctx, AddToOrderArgs(dish_id=5))  # McSpicy needs a sauce
    assert not result.ok and result.error is not None and result.error.code == "incomplete"
    assert result.update is not None and result.update.order is not None  # the empty draft
    assert result.update.order.lines == [] and chat.ctx.order is None
    assert [r for r in server.requests if r[0] == "POST" and r[1] == "/orders"]


def test_cancel_order_returns_the_instruction_to_clear_the_order() -> None:
    chat, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4, "options": [{"option_id": 1}]}, chat)
    before = chat.ctx.order
    result = CancelOrder().run(chat.ctx, CancelOrderArgs())
    assert result.ok and result.update is not None and result.update.clear_order
    assert chat.ctx.order is before  # not cleared by the tool itself


def test_note_need_returns_the_need_and_leaves_the_chat_needs_alone() -> None:
    chat, _, _ = make_order_tools()
    result = NoteNeed().run(chat.ctx, NoteNeedArgs(allergies=["milk"], veg_only=True))
    assert result.update is not None
    assert result.update.allergies == ["milk"] and result.update.veg_only is True
    assert chat.ctx.allergies == () and chat.ctx.veg_only is False


def test_set_customer_returns_the_customer_and_usual_dishes() -> None:
    chat, _, _ = make_order_tools()
    result = SetCustomer().run(chat.ctx, SetCustomerArgs(phone=PHONE, digits_confirmed=True))
    assert result.ok and result.update is not None and result.update.customer is not None
    assert result.update.usual is not None
    assert chat.ctx.customer is None  # not set by the tool itself


def test_the_context_cannot_be_changed_in_place() -> None:
    chat, _, _ = make_order_tools()
    try:
        chat.ctx.order = None  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("the context was changed in place")


def test_after_makes_the_next_context_from_an_update() -> None:
    chat, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4, "options": [{"option_id": 1}]}, chat)
    assert chat.ctx.order is not None and len(chat.ctx.order.lines) == 1
    tools.dispatch("note_need", {"allergies": ["milk"]}, chat)
    tools.dispatch("note_need", {"allergies": ["milk", "soy"], "veg_only": True}, chat)
    assert chat.ctx.allergies == ("milk", "soy") and chat.ctx.veg_only is True  # added, no repeats
    tools.dispatch("cancel_order", {}, chat)
    assert chat.ctx.order is None
