"""One session is one order: it starts anonymous, shows the cart to the model, and ends when the
order is placed or the customer leaves."""

import pytest

from app.backend.client import BackendClient
from app.backend.errors import BackendUnavailable
from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.session.session import SessionClosed
from tests.support.builders import context_of, make_session


def call(name: str, id: str = "c", **args: object) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=id, name=name, arguments=dict(args))])


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def test_a_new_session_is_open_with_nobody_identified_and_no_order() -> None:
    session, _, server = make_session([])
    assert session.status == "open" and session.customer is None
    assert session.order.latest is None and server.requests == []


def test_the_model_sees_the_cart_on_the_next_turn() -> None:
    session, llm, _ = make_session(
        [call("add_to_order", "a", dish_id=4, quantity=2), say("Added."), say("Sure.")]
    )
    session.send("two tikki burgers")
    assert "Order so far: empty" in context_of(llm.calls[0])
    session.send("what do I have?")
    assert "- line 10: 2 x McAloo Tikki = 152.38" in context_of(llm.calls[-1])


def test_placing_the_order_ends_the_session() -> None:
    session, _, _ = make_session(
        [call("add_to_order", "a", dish_id=4), call("place_order", "p"), say("Order 14, thanks.")]
    )
    assert session.send("one tikki, place it").stop_reason == "answered"
    assert session.status == "placed" and session.order.latest is not None
    assert session.order.latest.order_number == 14
    with pytest.raises(SessionClosed):
        session.send("and a coke")


def test_abandoning_cancels_the_draft_once() -> None:
    session, _, server = make_session([call("add_to_order", "a", dish_id=4), say("Added.")])
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
    assert session.status == "abandoned" and server.requests == []


def test_a_placed_order_is_not_cancelled_when_the_chat_closes() -> None:
    session, _, server = make_session(
        [call("add_to_order", "a", dish_id=4), call("place_order", "p"), say("Done.")]
    )
    session.send("one tikki, place it")
    session.abandon()
    assert session.status == "placed" and server.status == "confirmed"
    assert ("DELETE", "/orders/7") not in server.requests


def test_the_chat_ends_even_if_the_draft_cannot_be_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _, _ = make_session([call("add_to_order", "a", dish_id=4), say("Added.")])
    session.send("one tikki")

    def down(self: BackendClient, order_id: int) -> None:
        raise BackendUnavailable("down")

    monkeypatch.setattr(BackendClient, "cancel_order", down)
    session.abandon()
    assert session.status == "abandoned"
