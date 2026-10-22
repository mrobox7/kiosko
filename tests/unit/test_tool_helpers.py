"""The helpers the order tools share: how a refusal is said, when a request is repeated, how a
question reads."""

import pytest

from app.backend.errors import BackendConflict, BackendRuleViolation, BackendUnavailable
from app.backend.models import MenuOption, MenuOptionGroup
from app.menu.names import option_name
from app.tools.questions import INLINE, overview_of
from app.tools.recover import settle
from app.tools.refusals import translate


def refused(code: str, message: str = "m", *, missing=(), problems=()):
    return BackendRuleViolation(
        message, 422, code=code, missing=list(missing), problems=list(problems)
    )


def issue(code: str, message: str) -> dict:
    return {"line": 0, "code": code, "message": message}


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (refused("invalid_line", missing=[issue("required", "Sauce needs 1")]), "incomplete"),
        (refused("invalid_line", problems=[issue("too_many", "at most 1")]), "invalid_choice"),
        (refused("invalid_line", problems=[issue("no_such_meal", "no Small")]), "invalid_choice"),
        (refused("invalid_line", problems=[issue("unavailable", "off")]), "unavailable"),
        (refused("cannot_confirm", problems=[issue("price_changed", "now 9")]), "price_changed"),
        (refused("cannot_confirm", problems=[issue("unavailable", "off")]), "unavailable"),
        (refused("empty_order"), "empty_order"),
        (BackendConflict("closed", 409, code="order_closed"), "order_closed"),
        (refused("not_found", "No order 9"), "not_found"),
    ],
)
def test_each_refusal_gets_a_code_a_message_and_a_hint(exc, code) -> None:
    result = translate(exc)
    assert result is not None and result.error is not None and not result.ok
    assert result.error.code == code and result.error.message and result.error.hint


def test_a_problem_outranks_a_missing_answer() -> None:
    both = refused(
        "invalid_line",
        missing=[issue("required", "Sauce needs 1")],
        problems=[issue("unavailable", "Cheese is off")],
    )
    result = translate(both)
    assert result is not None and result.error is not None
    assert result.error.code == "unavailable" and result.error.message == "Cheese is off"


def test_the_messages_of_every_issue_are_kept() -> None:
    two = refused("invalid_line", problems=[issue("too_many", "A"), issue("unknown_option", "B")])
    result = translate(two)
    assert result is not None and result.error is not None and result.error.message == "A; B"


def test_a_refusal_it_does_not_know_is_left_to_the_caller() -> None:
    assert translate(refused("something_new")) is None
    assert translate(BackendRuleViolation("plain", 422)) is None


def test_settle_returns_the_first_answer_when_nothing_went_wrong() -> None:
    calls = []
    assert settle(lambda: calls.append(1) or "done", landed=lambda: "other") == "done"
    assert calls == [1]


def test_settle_looks_before_it_repeats_a_request_that_may_have_gone_through() -> None:
    seen = []

    def first() -> str:
        seen.append("sent")
        raise BackendUnavailable("lost", may_have_been_processed=True)

    assert settle(first, landed=lambda: "already there") == "already there"
    assert seen == ["sent"]


def test_settle_repeats_once_when_it_did_not_land_and_raises_a_second_failure() -> None:
    sent = []

    def first() -> str:
        sent.append(1)
        if len(sent) == 1:
            raise BackendUnavailable("lost", may_have_been_processed=True)
        return "ok"

    assert settle(first, landed=lambda: None) == "ok" and len(sent) == 2

    def always() -> str:
        raise BackendUnavailable("down", may_have_been_processed=True)

    with pytest.raises(BackendUnavailable):
        settle(always, landed=lambda: None)


def test_settle_does_not_repeat_a_request_that_never_left() -> None:
    sent = []

    def first() -> str:
        sent.append(1)
        raise BackendUnavailable("refused")  # could not connect: nothing was sent

    with pytest.raises(BackendUnavailable):
        settle(first, landed=lambda: "never asked")
    assert sent == [1]


def group(n: int, name: str = "Pick one", low: int = 1, high: int = 1) -> MenuOptionGroup:
    options = [MenuOption(id=i, name=f"Choice {i}", price_delta=0) for i in range(n)]
    return MenuOptionGroup(id=1, name=name, min_select=low, max_select=high, options=options)


def test_a_question_with_few_options_lists_them_and_with_many_gives_a_count() -> None:
    few = overview_of(group(INLINE))
    assert few["options"][0] == "Choice 0" and "options_count" not in few
    many = overview_of(group(INLINE + 1))
    assert many["options_count"] == INLINE + 1 and "options" not in many


def test_a_question_says_whether_it_is_required_and_how_many_to_pick() -> None:
    assert overview_of(group(2, low=1, high=1))["pick"] == "1"
    assert overview_of(group(2, low=0, high=3))["pick"] == "up to 3"
    assert overview_of(group(2, low=2, high=3))["pick"] == "2-3"
    assert overview_of(group(2, low=0, high=2))["required"] is False


def test_option_names_lose_symbols_but_keep_what_tells_them_apart() -> None:
    assert option_name("Coke® Zero (Can)") == "Coke Zero (Can)"
    assert option_name("Fries™ *Large*") == "Fries Large"
    option = MenuOption(id=1, name="Cheese ®", price_delta=28.57)
    assert overview_of(
        MenuOptionGroup(id=1, name="Cheese", min_select=0, max_select=1, options=[option])
    )["options"] == ["Cheese (+28.57)"]
