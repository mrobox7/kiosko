"""One session is one order: it starts anonymous, shows the cart to the model, and ends when the
order is placed or the customer leaves."""

import pytest

from app.backend.client import BackendClient
from app.backend.errors import BackendUnavailable
from app.session.session import SessionClosed
from tests.support.builders import context_of, make_session, plan, say

TIKKI = {"type": "add_item", "dish": "McAloo Tikki Burger"}
CHAT = {"type": "chat"}


def orders_asked(server):  # type: ignore[no-untyped-def]
    """The requests about orders (starting a chat reloads the menu, which is not one)."""
    return [r for r in server.requests if r[1].startswith("/orders")]


def placed_session():  # type: ignore[no-untyped-def]
    """A chat whose order was added, read back and placed over three messages."""
    session, llm, server = make_session(
        [
            plan(TIKKI), say("Added."),
            plan({"type": "read_back"}), say("Shall I place it?"),
            plan({"type": "place_order"}), say("Order 14, thanks."),
        ]
    )  # fmt: skip
    for text in ("one tikki", "that's all", "yes"):
        reply = session.send(text)
    return session, llm, server, reply


def test_a_new_session_is_open_with_nobody_identified_and_no_order() -> None:
    session, llm, server = make_session([])
    assert session.status == "open" and session.customer is None
    assert session.order is None and orders_asked(server) == [] and llm.calls == []


def test_the_model_sees_the_cart_on_the_next_turn() -> None:
    session, llm, _ = make_session(
        [
            plan({**TIKKI, "quantity": 2}), say("Added."),
            plan(CHAT), say("Sure."),
        ]
    )  # fmt: skip
    session.send("two tikki burgers")
    assert "Your order: empty." in context_of(llm.calls[0])
    assert "Dishes on it: McAloo Tikki" in context_of(
        llm.calls[1]
    )  # the reply is told what is on it
    assert "152.38" not in context_of(llm.calls[1])  # but no price: code writes those
    session.send("what do I have?")
    assert "line 10: 2 x McAloo Tikki" in context_of(llm.calls[2])


def test_placing_the_order_after_the_read_back_ends_the_session() -> None:
    session, _, _, reply = placed_session()
    assert reply.stop_reason == "answered"
    assert session.status == "placed" and session.order is not None
    assert session.order.order_number == 14
    with pytest.raises(SessionClosed):
        session.send("and a coke")


def test_abandoning_cancels_the_draft_once() -> None:
    session, _, server = make_session([plan(TIKKI), say("Added.")])
    session.send("one tikki")
    session.abandon()
    session.abandon()  # a second call changes nothing
    assert session.status == "abandoned" and server.status == "cancelled"
    assert server.requests.count(("DELETE", "/orders/7")) == 1
    with pytest.raises(SessionClosed):
        session.send("wait")


def test_abandoning_before_any_item_needs_no_request() -> None:
    session, _, server = make_session([])
    session.abandon()
    assert session.status == "abandoned" and orders_asked(server) == []


def test_a_placed_order_is_not_cancelled_when_the_chat_closes() -> None:
    session, _, server, _ = placed_session()
    session.abandon()
    assert session.status == "placed" and server.status == "confirmed"
    assert ("DELETE", "/orders/7") not in server.requests


def test_the_chat_ends_even_if_the_draft_cannot_be_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _, _ = make_session([plan(TIKKI), say("Added.")])
    session.send("one tikki")

    def down(self: BackendClient, order_id: int) -> None:
        raise BackendUnavailable("down")

    monkeypatch.setattr(BackendClient, "cancel_order", down)
    session.abandon()
    assert session.status == "abandoned"


def test_a_tap_on_the_screen_changes_the_order_the_next_message_sees() -> None:
    session, _, _ = make_session([plan({"type": "read_back"}), say("Here it is.")])
    result = session.act("add_to_order", {"dish_id": 4, "quantity": 2})
    assert result.ok and session.order is not None and len(session.order.lines) == 1
    reply = session.send("what do I have?")
    assert "2 × McAloo Tikki" in reply.text  # code reads the order back, quantity included
    session.act("place_order", {})
    assert session.status == "placed"
    with pytest.raises(SessionClosed):
        session.act("add_to_order", {"dish_id": 4})
