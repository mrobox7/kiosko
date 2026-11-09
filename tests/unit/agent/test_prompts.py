"""The supervisor's prompts: that they match the things the code accepts."""

from typing import get_args

from app.agent.items import Kind
from app.agent.prompts import RESPOND_PROMPT, SUPERVISOR_PROMPT, VOICE_PROMPT, greeting, outlet_line
from tests.support.builders import OUTLET_INFO


def test_every_kind_of_item_is_described_to_the_model() -> None:
    for kind in get_args(Kind):
        assert any(line.startswith(f"{kind} ") for line in SUPERVISOR_PROMPT.splitlines()), kind


def test_the_reply_writer_is_told_not_to_write_numbers_and_why_code_adds_them() -> None:
    assert "Never write a quantity, a price, a total or an order number" in RESPOND_PROMPT
    assert "the system adds the order summary" in RESPOND_PROMPT


def test_the_voice_rules_leave_the_order_summary_to_code() -> None:
    assert "Voice mode" in VOICE_PROMPT and "do not repeat it" in VOICE_PROMPT


def test_the_outlet_line_gives_the_name_and_the_address() -> None:
    line = outlet_line(OUTLET_INFO)
    assert OUTLET_INFO.name in line and OUTLET_INFO.address in line


NAME = "McDonald's Nemi Nagar"


def test_welcomes_at_the_outlet_and_asks_for_the_order() -> None:
    text = greeting(NAME)
    assert text.startswith(f"Welcome to {NAME}!") and "What can I get" in text


def test_stays_in_the_hosts_voice() -> None:
    text = greeting(NAME).lower()
    for technical in ("preference", "remember", "tool", "profile", "database", "allerg"):
        assert technical not in text


def test_every_prompt_has_a_role_an_input_rules_an_output_and_success_criteria() -> None:
    from app.agent.prompts import SEARCHER_PROMPT, SUPERVISOR_PROMPT

    for prompt in (SUPERVISOR_PROMPT, RESPOND_PROMPT, SEARCHER_PROMPT):
        headings = [line for line in prompt.splitlines() if line.isupper() and line.isalpha()]
        assert headings[:1] == ["ROLE"] and headings[-1] == "SUCCESS"
        assert {"ROLE", "INPUT", "RULES", "OUTPUT", "SUCCESS"} <= set(headings)
