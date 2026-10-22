"""The prompt text cannot drift from the tools it names or from the order flow."""

import re

from app.session.prompts import (
    MENU_HEADING,
    STABLE_PROMPT,
    VOICE_PROMPT,
    outlet_line,
    system_prompt,
)
from app.tools.registry import ToolRegistry
from tests.support.builders import OUTLET_INFO

PROMPTS = {"stable": STABLE_PROMPT, "voice": VOICE_PROMPT, "menu heading": MENU_HEADING}


def test_every_tool_the_prompts_name_exists() -> None:
    real = {spec.name for spec in ToolRegistry.discover().specs()}
    for where, text in PROMPTS.items():
        named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))
        assert named <= real, f"{where} names tools that do not exist: {sorted(named - real)}"


def test_the_prompts_name_the_tools_the_flow_depends_on() -> None:
    for tool in ("get_menu", "get_item", "add_to_order", "place_order", "cancel_order"):
        assert tool in STABLE_PROMPT


def test_nothing_is_left_of_the_booking_service() -> None:
    for where, text in PROMPTS.items():
        assert not re.search(r"reserv|booking|\bbook\b|\btables?\b", text, re.I), where


def test_the_rules_the_tool_descriptions_no_longer_carry_are_in_the_prompt() -> None:
    assert "milk means dairy" in STABLE_PROMPT and "before GST" in STABLE_PROMPT
    assert "never promise that a dish is free of an allergen" in STABLE_PROMPT


def test_the_order_is_read_back_and_placed_only_after_a_yes() -> None:
    assert "read back every line with the total" in STABLE_PROMPT
    assert "place_order only after a clear yes" in STABLE_PROMPT
    assert "Before cancel_order, ask the customer to confirm" in STABLE_PROMPT


def test_the_menu_outline_is_for_names_and_tools_are_for_facts() -> None:
    assert "lists only dish names by category" in STABLE_PROMPT
    assert "Do not call a tool for something the outline already answers" in STABLE_PROMPT


def test_the_outlet_comes_after_the_rules_and_before_the_outline() -> None:
    line = outlet_line(OUTLET_INFO)
    assert "McDonald's Nemi Nagar" in line and "Vaishali Nagar" in line
    full = system_prompt("burgers: McVeggie", OUTLET_INFO)
    assert full == f"{STABLE_PROMPT}\n\n{line}\n\n{MENU_HEADING}\nburgers: McVeggie"
    assert system_prompt() == STABLE_PROMPT  # no outlet given: nothing added
