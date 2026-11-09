"""The turn report: what really happened, as plain statements written by code, so the reply is
phrased from them and never reads a status, an id or a field name."""

import re

import pytest

from app.agent.context import open_questions, turn_report
from app.agent.items import HELD, LOOKUP_DOWN, Item
from app.agent.prompts import RESPOND_PROMPT
from app.backend.models import Line, Order


def item(kind: str, status: str, **more: object) -> Item:
    return Item(id="1.1", kind=kind, status=status, **more)  # type: ignore[arg-type]


def order(status: str = "draft", *names: str) -> Order:
    lines = [Line(id=i, name=n, quantity=1, line_total=1) for i, n in enumerate(names, 10)]
    return Order(id=1, status=status, lines=lines, subtotal=1, gst=0, total=1)


CASES = [
    (item("add", "done", result={"added": "Coke"}), "DONE: added Coke."),
    (item("remove", "done", result={"removed": "Coke"}), "DONE: removed Coke."),
    (item("change_qty", "done", result={"changed": "Coke"}), "DONE: changed the amount of Coke."),
    (item("place", "done"), "DONE: the order is placed."),
    (item("cancel", "done"), "DONE: the order is cancelled."),
    (
        item(
            "phone", "done", result={"identified": True, "name": "Asha", "usual_dishes": ["Coke"]}
        ),
        "DONE: saved the customer's phone number. Their name is Asha. "
        "Their usual dishes: Coke; you may offer one.",
    ),
    (
        item("need", "done", result={"noted": {"allergies": ["milk"], "veg_only": True}}),
        "DONE: noted that the customer is allergic to milk and eats only vegetarian food.",
    ),
    (item("search", "done", result="We have burgers."), "ANSWER: We have burgers."),
    (
        item("add", "needs_user", question="Which one?", candidates=["A", "B"]),
        "ASK: the system asks the customer this right after your reply, so do not ask it or repeat it: Which one? Choices: A, B.",
    ),
    (
        item(
            "add",
            "needs_user",
            question="'mc flurry' could be: A, B. Which one?",
            candidates=["A", "B"],
        ),
        "ASK: the system asks the customer this right after your reply, so do not ask it or repeat it: 'mc flurry' could be: A, B. Which one?",  # the choices are already in the question
    ),
    (
        item("phone", "needs_user", question="I heard 9 8. Is that right?"),
        "ASK: the system asks the customer this right after your reply, so do not ask it or repeat it: I heard 9 8. Is that right?",
    ),
    (
        item(
            "add",
            "failed",
            dish_text="pizza",
            result={"not_on_the_menu": "No.", "alternatives": ["McSpicy"]},
        ),
        "NOT SOLD: pizza is not on the menu. Close dishes: McSpicy.",
    ),
    (
        item(
            "add",
            "failed",
            dish_text="pizza",
            result={"not_on_the_menu": "No.", "alternatives": []},
        ),
        "NOT SOLD: pizza is not on the menu. Nothing close.",
    ),
    (
        item("place", "failed", result={"error": HELD}),
        "NOT DONE: placing the order has not happened yet, because other choices are still open. "
        "Say it will be done once those are settled.",
    ),
    (
        item("remove", "failed", result={"error": "No line 9", "hint": "Try again."}),
        "FAILED: removing that item did not work: No line 9. Try again.",
    ),
]


@pytest.mark.parametrize(("it", "line"), CASES)
def test_each_state_becomes_one_plain_statement(it: Item, line: str) -> None:
    assert turn_report([it], None).splitlines()[1] == line


def test_a_failed_lookup_is_reported_as_a_technical_problem_and_never_as_a_missing_dish() -> None:
    line = turn_report(
        [item("search", "failed", dish_text="pizza", result={"error": LOOKUP_DOWN})], None
    )
    assert "technical problem" in line and "Do not say the dish is missing" in line
    assert "unavailable" not in line  # no internal wording reaches the reply


def test_show_order_asks_the_system_to_read_the_order_and_changes_nothing() -> None:
    lines = turn_report([item("show_order", "done")], order("draft", "Coke")).splitlines()
    assert lines[1].startswith("SHOW:") and lines[-1].startswith("CHANGES: none")


def test_chat_adds_no_statement_and_a_quiet_turn_says_nothing_changed() -> None:
    lines = turn_report([item("chat", "done")], None).splitlines()
    assert lines == [
        "ORDER: nothing has been ordered yet.",
        "CHANGES: none. Nothing was added, removed, placed or cancelled this turn.",
    ]


def test_the_report_always_says_whether_the_order_is_placed() -> None:
    assert turn_report([], order("draft", "Coke", "Fries")).startswith(
        "ORDER: open and NOT placed yet. Dishes on it: Coke, Fries."
    )
    assert turn_report([], order("confirmed", "Coke")).startswith("ORDER: placed.")


def test_a_turn_with_something_done_says_only_the_done_lines_happened() -> None:
    last = turn_report([item("add", "done", result={"added": "Coke"})], None).splitlines()[-1]
    assert last == "CHANGES: only the DONE lines above happened."


def test_the_report_has_no_status_id_or_field_name_in_it() -> None:
    report = "\n".join(turn_report([it], None) for it, _ in CASES)
    for internal in (
        "needs_user",
        "needs_search",
        "status",
        "kind",
        "dish_text",
        "candidates",
        "{",
        "'id'",
    ):
        assert internal not in report, internal


def test_every_label_the_report_uses_is_explained_in_the_reply_prompt() -> None:
    report = "\n".join(turn_report([it], order("draft", "Coke")) for it, _ in CASES)
    report += "\n" + turn_report([item("show_order", "done")], None)
    labels = set(re.findall(r"^([A-Z ]+):", report, re.M))
    assert labels >= {
        "ORDER",
        "DONE",
        "ASK",
        "ANSWER",
        "SHOW",
        "NOT SOLD",
        "NOT DONE",
        "FAILED",
        "CHANGES",
    }
    for label in labels:
        assert f"  {label}" in RESPOND_PROMPT, label


def test_every_open_question_is_collected_for_code_to_ask() -> None:
    asking = item("add", "needs_user", question="Which size?", candidates=["S", "M"])
    done = item("remove", "done")
    assert open_questions([done, asking]) == ["Which size? Choices: S, M."]
    assert open_questions([done]) == []
