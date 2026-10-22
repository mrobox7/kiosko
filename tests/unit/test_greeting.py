from app.session.prompts import greeting

NAME = "McDonald's Nemi Nagar"


def test_welcomes_at_the_outlet_and_asks_for_the_order() -> None:
    text = greeting(NAME)
    assert text.startswith(f"Welcome to {NAME}!") and "What can I get" in text


def test_stays_in_the_hosts_voice() -> None:
    text = greeting(NAME).lower()
    for technical in ("preference", "remember", "tool", "profile", "database", "allerg"):
        assert technical not in text
