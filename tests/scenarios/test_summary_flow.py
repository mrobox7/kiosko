"""What the model receives on later turns: summary of older turns + the latest turn verbatim."""

from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.session.prompts import STABLE_PROMPT
from tests.support.builders import make_session

SLOT = "2030-06-10T19:30:00"


def call(name: str, id: str = "c", **args: object) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=id, name=name, arguments=dict(args))])


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def changing_part(system: str) -> str:
    return system.removeprefix(STABLE_PROMPT)


def user_texts(messages: list) -> list[str]:  # type: ignore[type-arg]
    return [m.text for m in messages if m.role == "user" and m.text]


def test_first_turns_have_no_summary_block() -> None:
    session, llm, _ = make_session([call("list_menu", "m"), say("Menu."), say("Sure.")])
    session.send("show the menu")
    assert "Earlier turns" not in changing_part(llm.calls[0].system)
    session.send("thanks")
    second = llm.calls[-1]
    assert "Earlier turns" not in changing_part(
        second.system
    )  # only the latest turn exists, and it is verbatim
    assert user_texts(second.messages) == ["show the menu", "thanks"]


def test_older_turns_become_summary_lines_and_latest_stays_verbatim() -> None:
    session, llm, _ = make_session(
        [
            call("list_menu", "m"),
            say("Menu."),
            call("check_availability", "a", slot_datetime=SLOT, party_size=2),
            say("Tables."),
            say("ok 3"),
            say("ok 4"),
            say("done"),
        ],
        summary_turns=2,
    )
    for text in ("t1 menu", "t2 tables", "t3", "t4", "t5"):
        assert session.send(text).stop_reason == "answered"

    last = llm.calls[-1]
    tail = changing_part(last.system)
    assert user_texts(last.messages) == ["t3", "t4", "t5"]  # chat-only t3 and latest t4, verbatim
    assert 'T2 asked: "t2 tables" | check_availability -> free 2030-06-10 19:30: table' in tail
    assert "T3 asked" not in tail  # chat-only turns are not summarised
    assert "T1 asked" not in tail and "T4 asked" not in tail
    assert user_texts(session.history) == [
        "t1 menu",
        "t2 tables",
        "t3",
        "t4",
        "t5",
    ]  # nothing dropped
    assert [s.number for s in session.summary] == [1, 2, 3, 4, 5]


def test_failed_turn_leaves_no_summary_entry() -> None:
    from app.llm.base import LLMError

    session, _, _ = make_session([LLMError("down"), say("fine")])
    assert session.send("hello").stop_reason == "llm_error"
    assert session.summary == []
    assert session.send("hello again").stop_reason == "answered"
    assert [s.number for s in session.summary] == [1]


def test_failed_turn_reports_what_was_already_changed() -> None:
    from app.llm.base import LLMError

    items = [{"menu_item_id": 1, "quantity": 1}]
    session, _, _ = make_session(
        [
            call("create_reservation", "c", table_id=7, slot_datetime=SLOT, party_size=2),
            say("Booked."),
            call("add_order_items", "a", reservation_id=1, items=items),
            LLMError("down"),
        ]
    )
    session.send("book table 7")
    reply = session.send("add paneer tikka")
    assert reply.stop_reason == "llm_error"
    assert "Changes already made: added to booking #1: order 1 item #1 x1." in reply.text


def test_chat_only_turns_stay_verbatim_so_an_answer_keeps_its_question() -> None:
    session, llm, _ = make_session(
        [
            say("When would you like to dine?"),
            say("Got it, 7pm. How many guests?"),
            say("Indoors or outdoors?"),
            say("Booking for 3, outdoors. Shall I check tables?"),
        ]
    )
    for text in ("i want to order", "today 7pm", "3", "outdoors"):
        session.send(text)

    last = llm.calls[-1]
    assert [(m.role, m.text) for m in last.messages] == [
        ("user", "i want to order"),
        ("assistant", "When would you like to dine?"),
        ("user", "today 7pm"),
        ("assistant", "Got it, 7pm. How many guests?"),
        ("user", "3"),
        ("assistant", "Indoors or outdoors?"),
        ("user", "outdoors"),
    ]
    assert "Earlier turns" not in changing_part(last.system)


def test_chat_only_turns_older_than_the_window_are_dropped() -> None:
    session, llm, _ = make_session([say("a"), say("b"), say("c"), say("d")], summary_turns=1)
    for text in ("t1", "t2", "t3", "t4"):
        session.send(text)
    assert user_texts(llm.calls[-1].messages) == ["t2", "t3", "t4"]
