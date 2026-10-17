from app.domain.state import WorkingState
from app.memory.profile import CustomerProfile
from app.session.context_builder import build_system_prompt
from app.session.prompts import STABLE_PROMPT
from tests.support.builders import NOW


def test_stable_first_volatile_last() -> None:
    state = WorkingState(reservation_id=5, slot_datetime=NOW, party_size=4, table_id=7)
    prompt = build_system_prompt("Priya", state, NOW, CustomerProfile())
    assert prompt.startswith(STABLE_PROMPT)
    tail = prompt.removeprefix(STABLE_PROMPT)
    assert "Saturday 2030-06-01 12:00" in tail and "Customer: Priya" in tail
    assert "Active reservation: #5" in tail and "table 7" in tail


def test_no_active_reservation() -> None:
    assert "Active reservation: none" in build_system_prompt(
        "A", WorkingState(), NOW, CustomerProfile()
    )
