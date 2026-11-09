"""How a dish's questions and options read to the model."""

from app.backend.models import Option, OptionGroup
from app.menu.names import option_name
from app.menu.questions import INLINE, overview_of


def group(n: int, name: str = "Pick one", low: int = 1, high: int = 1) -> OptionGroup:
    options = [Option(id=i, name=f"Choice {i}", price_delta=0) for i in range(n)]
    return OptionGroup(id=1, name=name, min_select=low, max_select=high, options=options)


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
    option = Option(id=1, name="Cheese ®", price_delta=28.57)
    assert overview_of(
        OptionGroup(id=1, name="Cheese", min_select=0, max_select=1, options=[option])
    )["options"] == ["Cheese (+₹28.57)"]
