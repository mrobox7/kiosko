from app.session.prompts import greeting


def test_greets_the_customer_by_first_name() -> None:
    assert greeting("Priya Sharma").startswith("Welcome, Priya. I'm DishPatch")


def test_works_without_a_usable_name() -> None:
    assert greeting("  ").startswith("Welcome. I'm DishPatch")


def test_stays_in_the_hosts_voice() -> None:
    text = greeting("Priya Sharma").lower()
    for technical in ("preference", "remember", "tool", "profile", "database", "allerg"):
        assert technical not in text
