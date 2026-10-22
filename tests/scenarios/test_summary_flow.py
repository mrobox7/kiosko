"""What the model receives on later turns: summary of older turns + the latest turn verbatim."""

from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.session.context_builder import HEADING
from app.session.prompts import STABLE_PROMPT, VOICE_PROMPT
from tests.support.builders import chat_texts, context_of, make_session


def call(name: str, id: str = "c", **args: object) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=id, name=name, arguments=dict(args))])


def say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def user_texts(messages: list) -> list[str]:  # type: ignore[type-arg]
    return [m.text for m in messages if m.role == "user" and m.text]


def test_first_turns_have_no_summary_block() -> None:
    session, llm, _ = make_session([call("get_menu", "m"), say("Menu."), say("Sure.")])
    session.send("show the menu")
    assert "Earlier turns" not in context_of(llm.calls[0])
    session.send("thanks")
    second = llm.calls[-1]
    assert "Earlier turns" not in context_of(
        second
    )  # only the latest turn exists, and it is verbatim
    assert user_texts(second.messages) == ["show the menu", "thanks"]


def test_older_turns_become_summary_lines_and_latest_stays_verbatim() -> None:
    session, llm, _ = make_session(
        [
            call("get_menu", "m"),
            say("Menu."),
            call("add_to_order", "a", dish_id=4),
            say("Added."),
            say("ok 3"),
            say("ok 4"),
            say("done"),
        ],
        summary_turns=2,
    )
    for text in ("t1 menu", "t2 add", "t3", "t4", "t5"):
        assert session.send(text).stop_reason == "answered"

    last = llm.calls[-1]
    tail = context_of(last)
    assert user_texts(last.messages) == ["t3", "t4", "t5"]  # chat-only t3 and latest t4, verbatim
    assert 'T2 asked: "t2 add" | said: "Added."' in tail  # add_to_order: the order shows it
    assert "add_to_order" not in tail
    assert "T3 asked" not in tail  # chat-only turns are not summarised
    assert "T1 asked" not in tail and "T4 asked" not in tail
    assert user_texts(session.history) == ["t1 menu", "t2 add", "t3", "t4", "t5"]  # nothing dropped
    assert [s.number for s in session.summary] == [1, 2, 3, 4, 5]


def test_a_turn_keeps_the_calls_the_order_cannot_show() -> None:
    session, llm, _ = make_session(
        [
            call("get_menu", "m"),
            call("add_to_order", "a", dish_id=4),
            say("Added a tikki."),
            say("ok"),
            say("done"),
        ],
        summary_turns=2,
    )
    for text in ("menu and a tikki", "ok", "thanks"):
        session.send(text)
    tail = context_of(llm.calls[-1])
    assert user_texts(llm.calls[-1].messages) == ["ok", "thanks"]  # the tool turn is not replayed
    assert "get_menu -> " in tail and "add_to_order" not in tail
    assert 'said: "Added a tikki."' in tail


def test_a_stated_allergy_is_still_in_the_context_long_after_its_turn_left_the_window() -> None:
    session, llm, _ = make_session(
        [
            call("note_need", "n", allergies=["milk"]),
            say("Noted."),
            *[say(f"r{i}") for i in range(6)],
        ]
    )
    for text in ("I am allergic to milk", *(f"t{i}" for i in range(6))):
        session.send(text)
    assert "allergic to milk" not in " ".join(user_texts(llm.calls[-1].messages))  # turn 1 is gone
    assert "Needs: allergic to milk" in context_of(llm.calls[-1])


def test_failed_turn_leaves_no_summary_entry() -> None:
    from app.llm.base import LLMError

    session, _, _ = make_session([LLMError("down"), say("fine")])
    assert session.send("hello").stop_reason == "llm_error"
    assert session.summary == []
    assert session.send("hello again").stop_reason == "answered"
    assert [s.number for s in session.summary] == [1]


def test_failed_turn_reports_what_was_already_changed() -> None:
    from app.llm.base import LLMError

    session, _, server = make_session(
        [
            call("add_to_order", "a", dish_id=4),
            say("Added."),
            call("add_to_order", "b", dish_id=5, options=[{"option_id": 1}]),
            LLMError("down"),
        ]
    )
    session.send("one tikki")
    reply = session.send("and a spicy chicken")
    assert reply.stop_reason == "llm_error"
    assert "Changes already made: order 7: added 1x McSpicy Chicken (line 11)" in reply.text
    assert len(server.lines) == 2  # the change is real, and the reply says so


def test_chat_only_turns_stay_verbatim_so_an_answer_keeps_its_question() -> None:
    session, llm, _ = make_session(
        [
            say("Sure. Which burger would you like?"),
            say("Tikki, got it. How many?"),
            say("With a meal or on its own?"),
            say("Three tikki burgers on their own. Shall I add them?"),
        ]
    )
    for text in ("i want a burger", "the tikki", "3", "on its own"):
        session.send(text)

    last = llm.calls[-1]
    assert chat_texts(last.messages) == [
        ("user", "i want a burger"),
        ("assistant", "Sure. Which burger would you like?"),
        ("user", "the tikki"),
        ("assistant", "Tikki, got it. How many?"),
        ("user", "3"),
        ("assistant", "With a meal or on its own?"),
        ("user", "on its own"),
    ]
    assert "Earlier turns" not in context_of(last)


def test_chat_only_turns_older_than_the_window_are_dropped() -> None:
    session, llm, _ = make_session([say("a"), say("b"), say("c"), say("d")], summary_turns=1)
    for text in ("t1", "t2", "t3", "t4"):
        session.send(text)
    assert user_texts(llm.calls[-1].messages) == ["t2", "t3", "t4"]


def test_spoken_turns_get_the_voice_rules_in_the_context_not_the_system_message() -> None:
    session, llm, _ = make_session([say("Sure."), say("Okay.")])
    session.send("a burger please", spoken=True)
    session.send("thanks")
    assert VOICE_PROMPT in context_of(llm.calls[0])
    assert VOICE_PROMPT not in context_of(llm.calls[1])
    assert llm.calls[0].system == llm.calls[1].system == STABLE_PROMPT


def test_system_message_is_the_same_fixed_text_on_every_call() -> None:
    session, llm, _ = make_session([call("get_menu", "m"), say("Menu."), say("Sure.")])
    session.send("show the menu")
    session.send("thanks")
    assert len(llm.calls) == 3
    assert {c.system for c in llm.calls} == {STABLE_PROMPT}
    for fact in ("2030", "Current date and time:", "Customer:", "Order so far"):
        assert fact not in STABLE_PROMPT


def test_context_is_its_own_message_before_the_bare_customer_text() -> None:
    session, llm, _ = make_session([say("Hi.")])
    session.send("hello there")
    roles = [(m.role, m.text) for m in llm.calls[0].messages]
    assert [r for r, _ in roles] == ["system", "user"]
    assert roles[0][1] and roles[0][1].startswith(f"{HEADING}:") and "Customer:" in roles[0][1]
    assert roles[1] == ("user", "hello there")  # nothing added to the customer's words
    assert [m.role for m in session.history] == ["user", "assistant"]  # context is not kept


def test_send_streams_the_reply_text_and_history_is_the_same_as_without_streaming() -> None:
    session, _, _ = make_session([say("Hello.")])
    pieces: list[str] = []
    reply = session.send("hi", on_text=pieces.append)
    assert "".join(pieces) == "Hello." == reply.text
    assert chat_texts(session.history) == [("user", "hi"), ("assistant", "Hello.")]
