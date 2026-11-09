"""Finding the dish the customer's words name, without a model."""

import pytest

from app.backend.models import Dish
from app.menu.fuzzy import pick
from app.menu.names import dish_name


def dish(i: int, name: str, kind: str = "item") -> Dish:
    return Dish(id=i, name=name, kind=kind, veg="veg", category="x", base_price=1)


MENU = [
    dish(1, "McAloo Tikki Burger ®"),
    dish(2, "Happy Meal McAloo Tikki Burger*", "combo"),
    dish(3, "McFlurry Oreo"),
    dish(4, "McFlurry Choc crunch"),
    dish(5, "Coke"),
    dish(6, "Coke ® Zero"),
    dish(7, "McSpicy Chicken"),
    dish(8, "McSpicy Chicken Meal*", "combo"),
    dish(9, "Pizza McPuff 2PC Meal", "combo"),
]


def chosen(text: str) -> tuple[str, list[str]]:
    verdict = pick(text, MENU)
    names = [dish_name(d.name) for d in verdict.candidates]
    return verdict.kind, [dish_name(verdict.dish.name)] if verdict.dish else names


@pytest.mark.parametrize("said", ["mc aloo tikki", "mcaloo tikki", "aloo tikki", "tikki burger"])
def test_spoken_variants_find_the_dish_even_where_the_spaces_fall_differently(said: str) -> None:
    assert chosen(said) == ("match", ["McAloo Tikki Burger"])


def test_a_combo_is_only_considered_when_the_customer_says_meal_or_combo() -> None:
    assert chosen("mc spicy chicken") == ("match", ["McSpicy Chicken"])  # not the Meal
    assert chosen("mcspicy chicken meal") == ("match", ["McSpicy Chicken Meal"])
    assert chosen("happy meal mcaloo tikki") == ("match", ["Happy Meal McAloo Tikki Burger"])


def test_the_whole_name_beats_a_longer_name_that_contains_it() -> None:
    assert chosen("coke") == ("match", ["Coke"])
    assert chosen("coke zero") == ("match", ["Coke Zero"])


def test_close_dishes_are_put_to_the_customer_and_not_picked() -> None:
    kind, names = chosen("mc flurry")
    assert kind == "ask" and names == ["McFlurry Oreo", "McFlurry Choc crunch"]
    assert chosen("mcflurry oreo") == ("match", ["McFlurry Oreo"])


@pytest.mark.parametrize("said", ["a drink", "pizza", "something spicy", "big mac"])
def test_what_is_not_a_dish_name_is_left_for_the_searcher(said: str) -> None:
    assert pick(said, MENU).kind == "none"
