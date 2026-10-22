"""get_menu against a stand-in menu."""

import json
from pathlib import Path

import httpx

from app.backend.client import BackendClient
from app.menu.menu import Menu
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.support.builders import clock


def product(
    i: int,
    name: str,
    category: str,
    price: float,
    veg: str = "veg",
    kind: str = "item",
    **extra: object,
):
    return {"id": i, "name": name, "description": None, "kind": kind, "veg": veg,
            "category": category, "base_price": price, "tags": [], **extra}  # fmt: skip


MENU = [
    product(1, "McAloo Tikki Burger", "burgers", 60.0),
    product(2, "McSpicy Chicken Burger", "burgers", 263.81, "non_veg"),
    product(3, "McVeggie Burger", "burgers", 150.0),
    product(4, "Fries", "fries-sides", 98.1),
    product(5, "Cold Coffee", "beverages", 124.76),
    product(6, "Burger Meal", "meals", 400.0, "non_veg", "combo"),
] + [product(10 + n, f"Soda {n}", "beverages", 50.0) for n in range(12)]


def setup(
    menu: list[dict] | None = None,
) -> tuple[ToolContext, list[dict[str, str]], ToolRegistry]:
    asked: list[dict[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append({"path": request.url.path, **request.url.params})
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"version": "v1"})
        return httpx.Response(
            200, json={"version": "v1", "products": MENU if menu is None else menu}
        )

    backend = BackendClient(
        httpx.Client(base_url="http://shop", transport=httpx.MockTransport(handle))
    )
    held = Menu(backend, "JPR-013-7429")
    ctx = ToolContext(backend=backend, clock=clock, outlet_code="JPR-013-7429", menu=held)
    held.refresh()  # loaded when the chat starts
    return ctx, asked, ToolRegistry.discover()


def get(**args: object) -> dict:
    ctx, _, tools = setup()
    result = tools.dispatch("get_menu", args, ctx)
    assert result.ok, result.error
    return result.data


def names(**args: object) -> list[str]:
    return [i["name"] for i in get(**args)["dishes"]]


def test_it_reads_the_list_the_chat_saved_and_asks_the_server_nothing() -> None:
    ctx, asked, tools = setup()
    assert asked[-1] == {"path": "/catalog", "outlet": "JPR-013-7429"}  # when the chat began
    asked.clear()
    assert tools.dispatch("get_menu", {}, ctx).ok
    assert tools.dispatch("get_menu", {"category": "burgers"}, ctx).ok
    assert asked == []


def test_names_are_written_the_way_the_customer_says_them() -> None:
    menu = [
        product(1, "McAloo Tikki Burger ®", "burgers", 60.0),
        product(2, "Spicy Paneer Burger(Any 2)+1 Med Fries", "meals", 300.0, "veg", "combo"),
    ]
    ctx, _, tools = setup(menu)
    items = tools.dispatch("get_menu", {"category": "burgers"}, ctx).data["dishes"]
    assert items[0]["name"] == "McAloo Tikki Burger"
    combo = tools.dispatch("get_menu", {"category": "meals"}, ctx).data["dishes"]
    assert combo[0]["name"] == "Spicy Paneer Burger" and combo[0]["combo"] is True


def test_no_arguments_lists_the_categories_in_menu_order() -> None:
    assert get() == {
        "categories": [
            {"category": "burgers", "dishes": 3},
            {"category": "fries-sides", "dishes": 1},
            {"category": "beverages", "dishes": 13},
            {"category": "meals", "dishes": 1},
        ]
    }


def test_filters_narrow_the_menu() -> None:
    assert names(category="burgers") == [
        "McAloo Tikki Burger",
        "McSpicy Chicken Burger",
        "McVeggie Burger",
    ]
    assert names(category="burgers", veg=True) == ["McAloo Tikki Burger", "McVeggie Burger"]
    assert names(category="burgers", veg=False) == ["McSpicy Chicken Burger"]
    assert names(category="burgers", max_price=150) == ["McAloo Tikki Burger", "McVeggie Burger"]
    assert names(max_price=60, veg=True)[0] == "McAloo Tikki Burger"  # across categories


def test_a_price_range_and_the_kind_of_item() -> None:
    assert names(category="burgers", min_price=100, max_price=200) == ["McVeggie Burger"]
    assert names(category="burgers", min_price=150) == [
        "McSpicy Chicken Burger",
        "McVeggie Burger",
    ]  # the price itself is included
    assert names(kind="combo") == ["Burger Meal"]
    assert "Burger Meal" not in names(kind="single")


def test_sorting_by_price_keeps_menu_order_for_equal_prices() -> None:
    assert names(category="burgers", sort="cheapest_first") == [
        "McAloo Tikki Burger",
        "McVeggie Burger",
        "McSpicy Chicken Burger",
    ]
    assert names(category="burgers", sort="priciest_first")[0] == "McSpicy Chicken Burger"
    assert names(category="beverages", sort="cheapest_first")[:3] == ["Soda 0", "Soda 1", "Soda 2"]
    last = get(category="beverages", sort="cheapest_first", page=2)["dishes"]
    assert [i["name"] for i in last] == ["Soda 10", "Soda 11", "Cold Coffee"]


def test_a_filter_alone_is_enough_and_a_page_alone_is_not() -> None:
    assert "dishes" in get(kind="combo") and "dishes" in get(min_price=1)
    assert "categories" in get(page=2)


def test_a_price_limit_includes_the_price_itself() -> None:
    assert names(category="burgers", max_price=60) == ["McAloo Tikki Burger"]


def test_nothing_matching_is_an_empty_list_not_an_error() -> None:
    assert get(category="burgers", max_price=10) == {"dishes": []}


def test_an_item_is_lean() -> None:
    assert get(category="meals")["dishes"] == [
        {"dish_id": 6, "name": "Burger Meal", "price": 400.0, "veg": False, "combo": True}
    ]


def test_long_lists_come_ten_at_a_time() -> None:
    first = get(category="beverages")
    assert len(first["dishes"]) == 10 and first["more"] == 3
    last = get(category="beverages", page=2)
    assert len(last["dishes"]) == 3 and "more" not in last
    assert get(category="beverages", page=3) == {"dishes": []}


def test_the_categories_are_a_fixed_list_in_the_schema() -> None:
    spec = next(x for x in ToolRegistry.discover().specs() if x.name == "get_menu")
    assert spec.parameters["properties"]["category"]["enum"] == [
        "burgers", "wraps", "fries-sides", "meals", "mccaf", "beverages", "desserts", "condiments"
    ]  # fmt: skip


def test_the_fixed_list_matches_the_menu_in_the_seed() -> None:
    seed = json.loads((Path(__file__).parents[2] / "backend/seed/seed.json").read_text())
    spec = next(x for x in ToolRegistry.discover().specs() if x.name == "get_menu")
    assert spec.parameters["properties"]["category"]["enum"] == [
        c["slug"] for c in seed["categories"]
    ]


def test_a_category_the_outlet_has_nothing_in_is_just_empty() -> None:
    assert get(category="desserts") == {"dishes": []}


def test_bad_arguments_are_refused() -> None:
    ctx, _, tools = setup()
    for args in (
        {"category": "pizza"},
        {"category": "Burgers"},
        {"max_price": 0},
        {"min_price": -1},
        {"page": 0},
        {"veg": "maybe"},
        {"kind": "x"},
    ):
        assert not tools.dispatch("get_menu", args, ctx).ok


def test_compact_keeps_the_filters_and_the_ids() -> None:
    ctx, _, tools = setup()

    def line(**args: object) -> str:
        return tools.compact("get_menu", args, tools.dispatch("get_menu", args, ctx))

    assert line() == "menu categories: burgers 3, fries-sides 1, beverages 13, meals 1"
    assert line(category="burgers", veg=True, max_price=150) == (
        "menu (category burgers, veg, max 150): McAloo Tikki Burger (dish 1), "
        "McVeggie Burger (dish 3)"
    )
    assert line(kind="combo", min_price=300, sort="cheapest_first") == (
        "menu (min 300, combo, cheapest first): Burger Meal (dish 6)"
    )
    assert line(category="burgers", max_price=10) == "menu (category burgers, max 10): nothing"


# --- searching by nutrition, allergen and bestseller

FOODS = [
    product(1, "Veg Burger", "burgers", 100.0, nutrition={"protein_g": 9.0, "calories_kcal": 300},
            allergens=["gluten", "milk"]),
    product(2, "Chicken Burger", "burgers", 200.0, "non_veg",
            nutrition={"protein_g": 24.5, "calories_kcal": 420}, allergens=["gluten", "egg"],
            tags=["bestseller"]),
    product(3, "Double Chicken", "burgers", 260.0, "non_veg",
            nutrition={"protein_g": 38.0, "calories_kcal": 610},
            allergens=["gluten", "milk", "egg"]),
    product(4, "Cola", "beverages", 80.0, nutrition={"protein_g": 0.0, "calories_kcal": 0}),
    product(5, "Lime Soda", "beverages", 70.0, nutrition={"protein_g": 0.0, "calories_kcal": 90}),
    product(6, "Latte", "beverages", 120.0, nutrition={"protein_g": 6.0, "calories_kcal": 150},
            allergens=["milk"]),
    product(7, "Mystery Dip", "condiments", 10.0),  # no nutrition figures at all
]  # fmt: skip


def foods(**args: object) -> dict:
    ctx, _, tools = setup(FOODS)
    result = tools.dispatch("get_menu", args, ctx)
    assert result.ok, result.error
    return result.data


def test_drinks_without_milk() -> None:
    data = foods(category="beverages", without="milk")
    assert [i["name"] for i in data["dishes"]] == ["Cola", "Lime Soda"]
    assert "none is listed" in data["note"]  # not a promise that it is free of it


def test_high_protein_non_veg_burgers_show_the_protein_they_were_chosen_for() -> None:
    data = foods(category="burgers", veg=False, min_protein=20, sort="most_protein_first")
    assert [(i["name"], i["protein_g"]) for i in data["dishes"]] == [
        ("Double Chicken", 38.0),
        ("Chicken Burger", 24.5),
    ]


def test_a_dish_with_no_figure_cannot_meet_a_limit_on_it() -> None:
    assert [i["name"] for i in foods(category="condiments", min_protein=1)["dishes"]] == []
    assert [i["name"] for i in foods(category="condiments", max_calories=500)["dishes"]] == []
    assert [i["name"] for i in foods(category="condiments")["dishes"]] == ["Mystery Dip"]


def test_fewest_calories_puts_a_zero_calorie_drink_first_and_a_missing_figure_last() -> None:
    data = foods(sort="fewest_calories_first", max_calories=700)
    names = [i["name"] for i in data["dishes"]]
    assert names[0] == "Cola" and data["dishes"][0]["calories_kcal"] == 0
    assert names == ["Cola", "Lime Soda", "Latte", "Veg Burger", "Chicken Burger", "Double Chicken"]


def test_bestsellers_and_filters_combine() -> None:
    assert [i["name"] for i in foods(bestseller=True)["dishes"]] == ["Chicken Burger"]
    assert foods(bestseller=True, without="egg")["dishes"] == []


def test_a_plain_price_search_carries_no_estimates_note_and_no_nutrition() -> None:
    data = foods(category="burgers", max_price=250)
    assert "note" not in data and "protein_g" not in data["dishes"][0]


def test_only_the_menus_allergen_words_are_accepted() -> None:
    ctx, _, tools = setup(FOODS)
    refused = tools.dispatch("get_menu", {"without": "dairy"}, ctx)
    assert refused.error is not None and refused.error.code == "invalid_arguments"
