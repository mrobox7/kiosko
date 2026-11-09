"""get_item against a stand-in for the ordering server."""

from tests.support.builders import make_order_tools as setup


def get(**args: object) -> dict:
    ctx, _, tools = setup()
    result = tools.dispatch("get_item", args, ctx)
    assert result.ok, result.error
    return result.data


def refused(**args: object) -> tuple[str, str]:
    ctx, _, tools = setup()
    result = tools.dispatch("get_item", args, ctx)
    assert not result.ok and result.error
    return result.error.code, result.error.hint


def test_a_dish_by_name_shows_its_questions_and_meal_sizes() -> None:
    ctx, server, tools = setup()
    result = tools.dispatch("get_item", {"dish": "McAloo Tikki Burger"}, ctx)
    assert result.ok
    assert result.data == {
        "dish_id": 4,
        "name": "McAloo Tikki Burger",
        "price": 76.19,
        "veg": True,
        "questions": [
            {
                "question": "Sauce",
                "required": True,
                "pick": "1",
                "options": ["Complimentary Ketchup", "No Ketchup"],
            },
            {
                "question": "Cheese",
                "required": False,
                "pick": "up to 1",
                "options": ["Cheese (+₹28.57)", "Double Cheese (+₹58.1)"],
            },
        ],
        "meals": [
            {"size": "Medium", "extra_price": 148.57},
            {"size": "Large", "extra_price": 176.19},
        ],
    }
    assert server.requests == []  # the whole menu is held: looking at a dish costs no request


def test_an_id_gives_the_same_answer() -> None:
    assert get(dish_id=4) == get(dish="McAloo Tikki Burger")


def test_a_meal_size_adds_that_meals_side_and_drink() -> None:
    questions = get(dish="McAloo Tikki Burger", meal_size="Medium")["questions"]
    assert [q["question"] for q in questions] == [
        "Sauce",
        "Cheese",
        "Meal side (Medium)",
        "Meal drink (Medium)",
    ]
    assert questions[3]["options"] == ["Medium Coke", "Coke Zero", "Coke Zero Can"]


def test_a_large_meal_has_no_side_question() -> None:
    questions = get(dish="McAloo Tikki Burger", meal_size="Large")["questions"]
    assert [q["question"] for q in questions][2:] == ["Meal drink (Large)"]


def test_a_long_list_shows_only_its_count_until_it_is_opened() -> None:
    flavour = get(dish="Float")["questions"][0]
    assert flavour == {"question": "Flavour", "required": True, "pick": "1", "options_count": 10}


def test_opening_a_question_lists_all_its_options() -> None:
    data = get(dish="Float", question="Flavour")
    assert len(data["options"]) == 10
    assert data["options"][-1] == "Cola Float (+₹10)"
    assert "of" not in data


def test_contains_keeps_only_matching_options_and_says_how_many_there_were() -> None:
    data = get(dish="Float", question="Flavour", contains="cola")
    assert data["options"] == ["Cola Float (+₹10)"]
    assert data["of"] == 10


def test_contains_with_no_match_gives_an_empty_list() -> None:
    data = get(dish="Float", question="Flavour", contains="fanta")
    assert data["options"] == [] and data["of"] == 10


def test_a_meal_question_is_opened_with_its_meal_size() -> None:
    data = get(dish="McAloo Tikki Burger", question="Meal drink", meal_size="Medium")
    assert data["question"] == "Meal drink (Medium)"
    assert data["options"] == ["Medium Coke", "Coke Zero", "Coke Zero Can"]


def test_a_meal_question_without_a_size_asks_for_one() -> None:
    code, hint = refused(dish="McAloo Tikki Burger", question="Meal drink")
    assert code == "needs_meal_size"
    assert "Medium" in hint and "Large" in hint


def test_a_question_of_the_other_meal_is_refused() -> None:
    code, _ = refused(dish_id=4, question="Meal side", meal_size="Large")
    assert code == "wrong_meal_size"


def test_an_unknown_question_lists_the_nearest() -> None:
    code, hint = refused(dish="McAloo Tikki Burger", question="Cheesy")
    assert code == "unknown_question"
    assert hint == "None are close"


def test_an_unknown_dish_lists_the_nearest() -> None:
    code, hint = refused(dish="McAloo Tikka")
    assert code == "unknown_dish"
    assert "McAloo Tikki Burger" in hint


def test_a_meal_size_the_dish_does_not_have_is_refused() -> None:
    code, hint = refused(dish="McSpicy Chicken", meal_size="Medium")
    assert code == "no_such_meal"
    assert hint == "It cannot be made a meal"


def test_an_id_the_outlet_does_not_sell_is_refused_by_the_server() -> None:
    ctx, _, tools = setup()
    result = tools.dispatch("get_item", {"dish_id": 99}, ctx)
    assert not result.ok


def test_the_dish_must_be_named_or_numbered_and_contains_needs_a_question() -> None:
    ctx, _, tools = setup()
    for args in ({}, {"dish": "Float", "dish_id": 6}, {"dish": "Float", "contains": "x"}):
        assert tools.dispatch("get_item", args, ctx).error.code == "invalid_arguments", args  # type: ignore[union-attr]


def test_nutrition_is_given_with_a_note_that_it_is_an_estimate() -> None:
    data = get(dish="McAloo Tikki Burger", info="nutrition")
    assert data["nutrition"]["calories_kcal"] == 339
    assert set(data) == {"dish_id", "name", "nutrition", "note"}
    assert "estimates" in data["note"]


def test_allergens_are_listed() -> None:
    data = get(dish_id=4, info="allergens")
    assert data["allergens"] == ["gluten", "soy"]
    assert "allergens_note" not in data


def test_no_listed_allergens_is_not_called_allergen_free() -> None:
    data = get(dish_id=5, info="allergens")
    assert data["allergens"] == []
    assert "not mean it was checked" in data["allergens_note"]


def test_info_is_asked_on_its_own() -> None:
    ctx, _, tools = setup()
    for extra in ({"question": "Sauce"}, {"meal_size": "Medium"}, {"contains": "x"}):
        result = tools.dispatch("get_item", {"dish_id": 4, "info": "nutrition", **extra}, ctx)
        assert result.error and result.error.code == "invalid_arguments", extra
