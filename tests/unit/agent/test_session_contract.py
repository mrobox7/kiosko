"""What the session and the page expect of the graph: the start run, the guard, trace events, the
chat's status, phone and needs, voice, and the order summary that code (not the model) writes."""

from typing import Any

import pytest

from app.agent.graph import build_graph, make_saver
from app.agent.items import Item
from app.agent.nodes.respond import CLOSING
from app.agent.order_summary import order_summary, spoken_amount, words
from app.agent.services import Services
from app.llm.contract import LLMResponse, Usage
from app.llm.messages import ToolCall
from app.session.session import Session
from tests.support.builders import OUTLET_INFO, clock, make_ctx, make_session, plan, say
from tests.support.fake_llm import FakeLLM
from tests.support.fake_order_server import FakeOrderServer


def build(script: list[Any], **limits: Any) -> tuple[Any, FakeLLM, dict[str, Any], Services, Any]:
    ctx = make_ctx(FakeOrderServer())
    llm = FakeLLM(script)
    services = Services(
        backend=ctx.backend, menu=ctx.menu, llm=llm, clock=clock, outlet=OUTLET_INFO, **limits
    )
    saver = make_saver()
    config = {"configurable": {"thread_id": "chat-1"}}
    return build_graph(services, saver), llm, config, services, saver


def send(graph: Any, config: dict[str, Any], text: str, **more: Any) -> dict[str, Any]:
    return graph.invoke({"kind": "message", "user_text": text, **more}, config)


def understood(
    *items: dict[str, Any], updates: list[dict[str, Any]] | None = None, **top: Any
) -> LLMResponse:
    body = {"language": "en", "items": list(items), "updates": updates or [], **top}
    return LLMResponse(tool_calls=[ToolCall(id="u", name="record_request", arguments=body)])


TIKKI = {"kind": "add", "dish_text": "McAloo Tikki Burger"}


# --- the start run


def test_starting_a_chat_makes_no_model_call_and_opens_it() -> None:
    graph, llm, config, _, _ = build([])
    out = graph.invoke({"kind": "start"}, config)
    assert llm.calls == [] and out["stop_reason"] == "started"
    state = graph.get_state(config).values
    assert state["status"] == "open" and state["outlet"] == OUTLET_INFO


# --- the guard


def test_an_empty_or_too_long_message_is_refused_without_a_model_call() -> None:
    graph, llm, config, _, _ = build([], max_chars=10)
    empty = send(graph, config, "   ")
    assert empty["stop_reason"] == "empty" and "type a message" in empty["reply"]
    long = send(graph, config, "x" * 11)
    assert long["stop_reason"] == "too_long" and "10 characters" in long["reply"]
    assert llm.calls == []


def test_too_many_messages_a_minute_are_refused() -> None:
    chat = {"kind": "chat"}
    script = [understood(chat, reply="Hi!"), understood(chat, reply="Hi again!")]
    graph, llm, config, _, _ = build(script, turns_per_min=2)
    send(graph, config, "hi")
    send(graph, config, "hi")
    third = send(graph, config, "hi")
    assert third["stop_reason"] == "rate_limit" and len(llm.calls) == 2


def test_a_chat_that_used_its_token_budget_is_refused() -> None:
    spent = LLMResponse(
        tool_calls=[
            ToolCall(
                id="u",
                name="record_request",
                arguments={"reply": "Hi!", "items": [{"kind": "chat"}]},
            )
        ],
        usage=Usage(input_tokens=100, output_tokens=10),
    )
    graph, llm, config, _, _ = build([spent], token_budget=100)
    send(graph, config, "hi")
    second = send(graph, config, "hi again")
    assert second["stop_reason"] == "token_budget" and len(llm.calls) == 1


# --- trace events


def test_a_turn_returns_its_trace_events_in_order() -> None:
    graph, _, config, _, _ = build([understood(TIKKI), say("Added.")])
    out = send(graph, config, "a tikki burger")
    names = [type(e).__name__ for e in out["events"]]
    assert names == [
        "GuardDecided",
        "LLMCalled",
        "ItemsRecorded",
        "ActionRun",
        "LLMCalled",
        "TurnEnded",
    ]
    ran = next(e for e in out["events"] if type(e).__name__ == "ActionRun")
    assert (ran.name, ran.status) == ("add", "done")
    called = [e for e in out["events"] if type(e).__name__ == "LLMCalled"][1]
    assert (called.input_tokens, called.output_tokens) == (200, 20)  # from the reply's usage


def test_the_events_start_afresh_each_turn() -> None:
    graph, _, config, _, _ = build([understood({"kind": "chat"}, reply="Hi!")] * 2)
    send(graph, config, "hi")
    second = send(graph, config, "hi again")
    assert [type(e).__name__ for e in second["events"]].count("GuardDecided") == 1


# --- status


def test_placing_the_order_closes_the_chat_and_the_reply_gives_the_number() -> None:
    graph, _, config, _, _ = build(
        [understood(TIKKI), say("Added."), understood({"kind": "place"}), say("Placed!")]
    )
    send(graph, config, "a tikki burger")
    out = send(graph, config, "place it")
    assert out["status"] == "placed"
    assert (
        out["reply"] == "Placed!\nOrder placed. Your number is 14.\n1 × McAloo Tikki\nTotal ₹80.00"
    )


# --- phone and needs


def test_a_phone_number_is_read_back_and_only_taken_once_confirmed() -> None:
    graph, _, config, _, _ = build(
        [
            understood({"kind": "phone", "phone": "98765 43210"}),
            say("Is 9 8 7 6 5 4 3 2 1 0 right?"),
            understood(updates=[{"id": "1.1", "digits_confirmed": True}]),
            say("Thanks, you're set."),
        ]
    )
    out = send(graph, config, "my number is 98765 43210")
    assert (
        out["items"][0].status == "needs_user" and "9 8 7 6 5 4 3 2 1 0" in out["items"][0].question
    )
    assert graph.get_state(config).values.get("customer") is None

    out = send(graph, config, "yes")
    assert out["items"] == [] and graph.get_state(config).values["customer"].phone.endswith(
        "9876543210"
    )


def test_what_the_customer_cannot_eat_is_kept_and_shown_to_the_next_call() -> None:
    need = {"kind": "need", "allergies": ["milk"], "veg_only": True}
    graph, llm, config, _, _ = build(
        [understood(need), say("Noted."), understood({"kind": "chat"}, reply="Ok")]
    )
    send(graph, config, "i am allergic to milk and only eat veg")
    state = graph.get_state(config).values
    assert state["allergies"] == ["milk"] and state["veg_only"] is True
    send(graph, config, "thanks")
    assert "allergic to milk; vegetarian only" in llm.calls[-1].messages[-2].text


# --- voice


def test_a_spoken_turn_gets_the_voice_rules_and_a_summary_in_words() -> None:
    graph, llm, config, _, _ = build([understood(TIKKI), say("Added.")])
    out = send(graph, config, "a tikki burger", spoken=True)
    assert "Voice mode" in llm.calls[1].system
    assert (
        out["reply"] == "Added. You have one McAloo Tikki. The total is eighty rupees. " + CLOSING
    )


def test_a_typed_turn_gets_no_voice_rules() -> None:
    graph, llm, config, _, _ = build([understood(TIKKI), say("Added.")])
    send(graph, config, "a tikki burger")
    assert "Voice mode" not in llm.calls[1].system


# --- the order summary, in code


def test_numbers_in_words() -> None:
    assert [words(n) for n in (0, 7, 14, 80, 251, 1200)] == [
        "zero", "seven", "fourteen", "eighty", "two hundred fifty one", "one thousand two hundred",
    ]  # fmt: skip
    assert spoken_amount(251.05) == "two hundred fifty one rupees and five paise"


def test_the_summary_is_only_written_when_the_order_changed() -> None:
    from app.backend.models import Line, Order

    order = Order(
        id=1, status="draft", subtotal=1, gst=0, total=251.0,
        lines=[Line(id=1, name="Coke", quantity=2, line_total=1)],
    )  # fmt: skip
    changed = Item(id="1", kind="add", status="done")
    asked = Item(id="2", kind="add", status="needs_user")
    assert order_summary(order, [asked], False) == ""
    shown = Item(id="3", kind="show_order", status="done")
    assert order_summary(order, [shown], False) == "Your order:\n2 × Coke\nTotal ₹251.00"
    assert order_summary(order, [changed], False) == "Your order:\n2 × Coke\nTotal ₹251.00"
    assert order_summary(order, [changed], True) == (
        "You have two Coke. The total is two hundred fifty one rupees."
    )


# --- the session runs on this graph unchanged


def test_the_session_runs_over_the_supervisor_graph() -> None:
    graph, llm, _, services, saver = build([understood(TIKKI), say("Added.")])
    session = Session(graph, saver, services, "chat-2")  # type: ignore[arg-type]
    assert session.status == "open" and llm.calls == []  # the start run made no model call
    reply = session.send("a tikki burger")
    assert reply.text.startswith("Added.") and reply.stop_reason == "answered"
    assert [type(e).__name__ for e in reply.events][0] == "GuardDecided"
    assert session.order is not None and len(session.order.lines) == 1
    session.abandon()
    assert session.status == "abandoned" and session.order is not None
    assert session.order.status == "cancelled"


# --- a missing choice is always asked, by code, about the right dish


def _asked_float(words: str) -> str:
    session, _, server = make_session([plan({"type": "add_item", "dish": "float"}), say(words)])
    reply = session.send("a float").text
    assert server.lines == []  # nothing is added without its flavour
    return reply


@pytest.mark.parametrize("words", ["", "Sure thing!", "Which size would you like?"])
def test_a_missing_choice_is_asked_by_code_whatever_the_model_said(words: str) -> None:
    reply = _asked_float(words)
    assert "For the Float, which Flavour?" in reply
    assert reply.endswith("options.")  # the question is last, so the customer answers it


def test_the_question_follows_the_order_summary() -> None:
    session, _, _ = make_session(
        [
            plan(
                {"type": "add_item", "dish": "mcspicy", "options": ["Tomato Ketchup"]},
                {"type": "add_item", "dish": "float"},
            ),
            say("Spicy added."),
        ]
    )
    reply = session.send("a mcspicy and a float").text
    assert reply.index("Your order:") < reply.index("For the Float, which Flavour?")


def test_a_turn_with_only_questions_needs_no_model_words() -> None:
    session, llm, _ = make_session([plan({"type": "add_item", "dish": "float"})])
    reply = session.send("a float").text
    assert reply.startswith("For the Float, which Flavour?")
    assert len(llm.calls) == 1  # the supervisor only: nothing was left for the model to claim


def test_a_model_that_returns_nothing_is_asked_once_more() -> None:
    session, llm, _ = make_session(
        [
            plan({"type": "add_item", "dish": "mcspicy", "options": ["Tomato Ketchup"]}),
            say(""),
            say("Done."),
        ]
    )
    assert session.send("a mcspicy").text.startswith("Done.")
    assert len(llm.calls) == 3


def test_the_closing_question_is_asked_only_when_nothing_else_is_open() -> None:
    graph, _, config, _, _ = build([understood(TIKKI), say("Added.")])
    assert send(graph, config, "a tikki burger")["reply"].endswith(CLOSING)
    assert CLOSING not in _asked_float("")  # a choice is still open, so that is the question
