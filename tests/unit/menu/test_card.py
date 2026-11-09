"""The menu card the supervisor's models are given in place of the full outline."""

from app.backend.models import Category, Dish
from app.menu.card import SHOWN, render_card

CATEGORIES = [
    Category(slug="burgers", name="Burgers"),
    Category(slug="beverages", name="Beverages"),
    Category(slug="empty", name="Nothing Here"),
]


def dish(i: int, name: str, category: str, veg: str = "veg", tags: tuple[str, ...] = ()) -> Dish:
    return Dish(
        id=i, name=name, kind="item", veg=veg, category=category, base_price=1, tags=list(tags)
    )


DISHES = [
    dish(1, "McAloo Tikki Burger ®", "burgers"),
    dish(2, "McSpicy Chicken", "burgers", "non_veg"),
    dish(3, "Coke", "beverages"),
    dish(4, "Sprite", "beverages"),
]


def test_each_section_shows_its_slug_its_diets_and_its_dishes() -> None:
    card = render_card(CATEGORIES, DISHES).splitlines()
    assert card == [
        "Burgers [burgers]: veg + non-veg - McAloo Tikki Burger, McSpicy Chicken",
        "Beverages [beverages]: veg - Coke, Sprite",
    ]  # a section with no dishes is not offered, and a short list has no "more"


def test_a_long_section_names_five_dishes_and_says_how_many_more() -> None:
    many = [dish(i, f"Shake {i}", "beverages") for i in range(8)]
    line = render_card(CATEGORIES, many)
    assert line.endswith(f"Shake 4 (+{8 - SHOWN} more)") and "Shake 5" not in line


def test_bestsellers_come_first_and_names_are_not_repeated() -> None:
    menu = [
        dish(1, "Plain Shake", "beverages"),
        dish(2, "Cold Coffee", "beverages", tags=("bestseller",)),
        dish(3, "Cold Coffee ®", "beverages"),
    ]
    assert render_card(CATEGORIES, menu).endswith("Cold Coffee, Plain Shake")


def test_a_non_veg_only_section_is_said_so() -> None:
    card = render_card(CATEGORIES, [dish(1, "Chicken Wings", "burgers", "non_veg")])
    assert "non-veg - Chicken Wings" in card


def test_a_section_the_menu_does_not_name_is_still_on_the_card() -> None:
    card = render_card([], [dish(1, "Latte", "fries-sides")])
    assert card == "Fries Sides [fries-sides]: veg - Latte"
