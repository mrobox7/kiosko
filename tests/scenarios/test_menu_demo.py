"""Menu demo and the stage 2 conversation flows, through Session, loop, tools and fake backend."""

from app.agent.events import ToolRequested
from app.domain.messages import ToolCall
from app.llm.base import LLMError, LLMResponse
from tests.support.builders import make_session

SLOT = "2030-06-10T19:30:00"


def call(name: str, id: str = "c", **args: object) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=id, name=name, arguments=args)])


def test_vegetarian_starters_under_400() -> None:
    args = {"category": "starter", "tags_any": ["vegetarian"], "max_price": 400}
    session, llm, _ = make_session(
        [call("list_menu", **args), LLMResponse(text="Paneer Tikka, Hara Bhara Kabab, Samosa.")]
    )
    reply = session.send("What vegetarian starters do you have under 400?")
    assert reply.stop_reason == "answered" and "Samosa" in reply.text
    requested = [e for e in reply.events if isinstance(e, ToolRequested)]
    assert requested[0].name == "list_menu" and requested[0].arguments == args
    tool_content = llm.calls[1].messages[-1].tool_outcomes[0].content
    assert "Chicken Tikka" not in tool_content and "Samosa" in tool_content


def test_booking_then_order_in_a_later_turn_uses_working_state() -> None:
    session, llm, backend = make_session(
        [
            call("check_availability", slot_datetime=SLOT, party_size=4, location="outdoor"),
            call("create_reservation", table_id=7, slot_datetime=SLOT, party_size=4),
            LLMResponse(text="Booked table 7. Anything to order?"),
            call("add_order_items", reservation_id=1, items=[{"menu_item_id": 1, "quantity": 2}]),
            LLMResponse(text="Added two Paneer Tikka."),
        ],
        customer_id=1,
    )
    session.send("Book outdoor for 4 on 10 June at 19:30")
    assert session.state.reservation_id == 1 and session.state.table_id == 7
    session.send("Add two paneer tikka to that")
    # The 2nd turn's system prompt carries the active reservation; history carried over.
    assert "Active reservation: #1" in llm.calls[3].system
    assert len(llm.calls[3].messages) > 3
    assert [e.action for e in session.ledger] == ["created", "added"]
    assert backend.orders[1]["reservation_id"] == 1


def test_backend_rejection_reaches_the_model_verbatim() -> None:
    session, llm, backend = make_session(
        [
            call("create_reservation", table_id=7, slot_datetime=SLOT, party_size=4),
            LLMResponse(text="That table is taken."),
        ],
        customer_id=1,
    )
    backend.add_reservation(2, 7, SLOT, 4)
    session.send("book table 7")
    content = llm.calls[1].messages[-1].tool_outcomes[0].content
    assert "Table 7 is already booked at this slot" in content
    assert session.ledger == [] and session.state.reservation_id is None


def test_cannot_act_on_another_customers_reservation() -> None:
    session, llm, backend = make_session(
        [call("cancel_reservation", reservation_id=1), LLMResponse(text="Not allowed.")],
        customer_id=1,
    )
    backend.add_reservation(2, 7, SLOT, 4)  # Rahul's booking
    session.send("cancel reservation 1")
    assert "not_permitted" in llm.calls[1].messages[-1].tool_outcomes[0].content
    assert backend.writes() == []
    assert backend.reservations[1]["status"] == "confirmed"


def test_cancel_clears_working_state() -> None:
    session, _, _ = make_session(
        [
            call("create_reservation", table_id=7, slot_datetime=SLOT, party_size=4),
            LLMResponse(text="Booked."),
            call("cancel_reservation", reservation_id=1),
            LLMResponse(text="Cancelled."),
        ]
    )
    session.send("book")
    session.send("cancel it")
    assert session.state.reservation_id is None
    assert [e.action for e in session.ledger] == ["created", "cancelled"]


def test_failed_turn_is_discarded_but_writes_are_reported() -> None:
    session, _, _ = make_session(
        [
            call("create_reservation", table_id=7, slot_datetime=SLOT, party_size=4),
            LLMError("down"),
        ]
    )
    reply = session.send("book table 7")
    assert reply.stop_reason == "llm_error"
    assert "Changes already made: Reservation #1" in reply.text
    assert session.history == []  # turn dropped, no unpaired tool call
    assert session.state.reservation_id == 1  # but the booking still resolves next turn
