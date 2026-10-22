"""Turning names into dish and option ids."""

import pytest

from app.backend.models import MenuDish
from app.tools.menu_lookup import LookupFailed, find_dish


def dish(i: int, name: str) -> MenuDish:
    return MenuDish(id=i, name=name, kind="item", veg="veg", category="x", base_price=1)


MENU = [
    dish(1, "McAloo Tikki Burger ®"),
    dish(2, "Chicken McNuggets® 6pc"),
    dish(3, "Chicken McNuggets® 20pc"),
    dish(4, "Coke"),
    dish(5, "Coke ® Zero"),
    dish(6, "Spicy Paneer/Spicy Chicken Burger(Any 2)+1 Med Fries+2 Puff"),
]


def found(name: str) -> int:
    return find_dish(MENU, name).id


def test_the_whole_name_matches_however_it_is_written() -> None:
    assert found("McAloo Tikki Burger ®") == found("mcaloo tikki burger") == 1
    assert found("Chicken McNuggets 6pc") == 2


def test_the_cut_name_from_the_outline_matches_a_long_combo() -> None:
    assert found("Spicy Paneer/Spicy Chicken Burger") == 6


def test_the_whole_name_beats_a_longer_name_that_contains_it() -> None:
    assert found("Coke") == 4 and found("coke zero") == 5


def test_all_the_words_of_exactly_one_name_are_enough() -> None:
    assert found("McAloo Tikki") == 1 and found("mcnuggets 6pc") == 2


def test_several_names_that_fit_are_not_guessed() -> None:
    with pytest.raises(LookupFailed) as caught:
        find_dish(MENU, "Chicken McNuggets")
    assert caught.value.code == "ambiguous_dish"
    assert (
        caught.value.hint
        == "Ask the customer which one: Chicken McNuggets 6pc, Chicken McNuggets 20pc"
    )


def test_an_unknown_name_gets_the_names_that_share_a_word() -> None:
    with pytest.raises(LookupFailed) as caught:
        find_dish(MENU, "Zero Sugar Drink")
    assert caught.value.code == "unknown_dish"
    assert caught.value.hint == "Closest: Coke Zero"
    with pytest.raises(LookupFailed) as caught:
        find_dish(MENU, "pizza")
    assert caught.value.hint == "None are close"


def test_an_empty_name_matches_nothing() -> None:
    with pytest.raises(LookupFailed):
        find_dish(MENU, "  ®  ")
