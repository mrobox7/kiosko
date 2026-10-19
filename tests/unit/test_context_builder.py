from datetime import timedelta

from app.backend.models import Reservation
from app.domain.state import WorkingState
from app.memory.profile import CustomerProfile
from app.session.context_builder import HEADING, build_context
from app.session.prompts import STABLE_PROMPT, VOICE_PROMPT, system_prompt
from tests.support.builders import NOW


def test_context_has_heading_time_customer_and_reservation() -> None:
    state = WorkingState(reservation_id=5, slot_datetime=NOW, party_size=4, table_id=7)
    context = build_context("Priya", state, NOW, CustomerProfile())
    assert context.startswith(f"{HEADING}:")
    assert "Saturday 2030-06-01 12:00" in context and "Customer: Priya" in context
    assert "Active reservation: #5" in context and "table 7" in context


def booking(rid: int, days: int) -> Reservation:
    return Reservation(
        id=rid, customer_id=1, table_id=7, slot_datetime=NOW.replace(tzinfo=None) + timedelta(days),
        party_size=4, status="confirmed",
    )  # fmt: skip


def test_no_active_line_when_nothing_is_being_worked_on() -> None:
    assert "Active reservation" not in build_context("A", WorkingState(), NOW, CustomerProfile())


def test_upcoming_bookings_are_listed_with_ids() -> None:
    context = build_context("A", WorkingState(), NOW, CustomerProfile(), [booking(5, 9)])
    assert "Upcoming bookings:\n- #5 Mon 2030-06-10 12:00, party of 4, table 7" in context


def test_no_upcoming_bookings_says_none() -> None:
    assert "Upcoming bookings: none" in build_context(
        "A", WorkingState(), NOW, CustomerProfile(), []
    )


def test_unknown_bookings_are_left_out_rather_than_called_none() -> None:
    context = build_context("A", WorkingState(), NOW, CustomerProfile(), None)
    assert "Upcoming bookings" not in context


def test_only_the_next_few_bookings_are_shown() -> None:
    many = [booking(i, i) for i in range(1, 6)]
    context = build_context("A", WorkingState(), NOW, CustomerProfile(), many)
    assert "#3 " in context and "#4 " not in context and "- and 2 more" in context


def test_voice_rules_are_part_of_the_fixed_system_message_for_spoken_turns() -> None:
    assert system_prompt(False) == STABLE_PROMPT
    assert system_prompt(True) == f"{STABLE_PROMPT}\n\n{VOICE_PROMPT}"


def test_context_never_contains_voice_rules() -> None:
    assert VOICE_PROMPT not in build_context("A", WorkingState(), NOW, CustomerProfile())


def test_the_rules_tell_the_model_to_name_the_options_it_offers() -> None:
    # The customer cannot see tool results, least of all on a call: "one of these" is useless.
    assert "name the options in that same reply" in STABLE_PROMPT
    assert "cannot see your tool results" in STABLE_PROMPT
