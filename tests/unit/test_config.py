import pytest

from app.config.settings import Settings


def test_defaults_and_fail_fast() -> None:
    s = Settings(_env_file=None, llm_api_key="")  # type: ignore[call-arg]
    assert (s.max_iterations, s.max_tool_calls_per_turn) == (16, 24)
    with pytest.raises(ValueError):
        s.require_llm()


def test_the_drive_thru_must_be_told_its_outlet() -> None:
    with pytest.raises(ValueError, match="OUTLET_CODE"):
        Settings(_env_file=None, outlet_code="").require_outlet()  # type: ignore[call-arg]
    Settings(_env_file=None, outlet_code="JPR-013-7429").require_outlet()  # type: ignore[call-arg]
