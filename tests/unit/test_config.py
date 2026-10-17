import pytest

from app.config.settings import Settings


def test_defaults_and_fail_fast() -> None:
    s = Settings(_env_file=None, llm_api_key="")  # type: ignore[call-arg]
    assert s.max_iterations == 8
    with pytest.raises(ValueError):
        s.require_llm()
