"""add_to_order against a stand-in for the ordering server."""

import httpx

from app.tools.registry import ToolRegistry
from tests.support.builders import make_order_tools as setup


def test_first_item_starts_the_order_and_replies_with_what_changed() -> None:
    ctx, server, tools = setup()
    args = {"dish_id": 4, "quantity": 2, "note": "no onions", "meal_size": "Medium"}
    result = tools.dispatch("add_to_order", args, ctx)
    assert result.ok
    assert result.data == {
        "order_id": 7,
        "added": {
            "line_id": 10,
            "name": "McAloo Tikki",
            "quantity": 2,
            "line_total": 152.38,
            "meal_size": "Medium",
            "note": "no onions",
        },
        "line_count": 1,
        "subtotal": 152.38,
        "gst": 7.62,
        "total": 160.0,
    }
    assert ctx.order.order_id == 7
    assert server.created_with == {"outlet": "JPR-013-7429"}  # the outlet code, not an id
    assert server.requests == [("POST", "/orders"), ("POST", "/orders/7/lines")]
    assert result.changed


def test_a_fifth_item_joins_the_same_order_and_the_totals_cover_all_five() -> None:
    ctx, server, tools = setup()
    for _ in range(5):
        result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.data["added"]["line_id"] == 14
    assert result.data["line_count"] == 5
    assert result.data["subtotal"] == 380.95
    assert server.requests.count(("POST", "/orders")) == 1
    assert "items" not in result.data


def test_options_are_listed_by_name_with_a_count_when_more_than_one() -> None:
    ctx, _, tools = setup()
    picks = [{"option_id": 1}, {"option_id": 2, "qty": 2}]
    result = tools.dispatch("add_to_order", {"dish_id": 5, "options": picks}, ctx)
    assert result.data["added"]["options"] == ["Ketchup", "2x Ketchup"]


def test_missing_choices_reach_the_model_and_nothing_is_added() -> None:
    ctx, server, tools = setup()
    result = tools.dispatch("add_to_order", {"dish_id": 5}, ctx)
    assert not result.ok and result.error is not None
    assert result.error.code == "incomplete"
    assert "Sauce:" in (result.error.hint or "")  # the questions are in the hint, said once
    assert "Sauce" not in result.error.message
    assert server.lines == [] and not result.changed


def test_a_refused_item_leaves_the_order_for_the_next_try() -> None:
    ctx, server, tools = setup()
    tools.dispatch("add_to_order", {"dish_id": 5}, ctx)
    result = tools.dispatch("add_to_order", {"dish_id": 5, "options": [{"option_id": 1}]}, ctx)
    assert result.ok and result.data["order_id"] == 7
    assert server.requests.count(("POST", "/orders")) == 1


def test_the_model_cannot_pass_an_order_id() -> None:
    ctx, _, tools = setup()
    result = tools.dispatch("add_to_order", {"dish_id": 4, "order_id": 99}, ctx)
    assert result.ok and ctx.order.order_id == 7


def test_the_summary_line_keeps_the_line_id_a_later_turn_needs() -> None:
    ctx, _, tools = setup()
    args = {"dish_id": 4, "quantity": 2}
    added = tools.dispatch("add_to_order", args, ctx)
    assert tools.compact("add_to_order", args, added) == (
        "order 7: added 2x McAloo Tikki (line 10), total 160.0"
    )
    refused = tools.dispatch("add_to_order", {"dish_id": 5}, ctx)
    assert tools.compact("add_to_order", {"dish_id": 5}, refused) == (
        "dish 5: not added (incomplete)"
    )


# --- naming the item and its choices


def test_the_tool_takes_a_name_or_an_id_for_the_item_and_for_each_choice() -> None:
    spec = next(s for s in ToolRegistry.discover().specs() if s.name == "add_to_order")
    assert set(spec.parameters["properties"]) == {
        "dish",
        "dish_id",
        "quantity",
        "meal_size",
        "options",
        "note",
    }
    assert "required" not in spec.parameters
    pick = spec.parameters["$defs"]["OptionPick"]["properties"]
    assert set(pick) == {"name", "option_id", "qty"}


def test_an_item_and_its_choices_can_be_sent_by_name() -> None:
    ctx, server, tools = setup()
    args = {"dish": "McAloo Tikki Burger", "options": [{"name": "No Ketchup"}, {"name": "Cheese"}]}
    result = tools.dispatch("add_to_order", args, ctx)
    assert result.ok, result.error
    assert result.data["added"]["name"] == "McAloo Tikki"  # what the order server named it
    assert server.requests == [  # the menu was loaded when the chat started: names cost nothing
        ("POST", "/orders"),
        ("POST", "/orders/7/lines"),
    ]
    assert server.sent == {
        "product_id": 4,
        "quantity": 1,
        "meal_size": None,
        "options": [{"option_id": 2, "qty": 1}, {"option_id": 4, "qty": 1}],
        "note": None,
    }


def test_ids_alone_make_no_lookup_requests() -> None:
    ctx, server, tools = setup()
    tools.dispatch("add_to_order", {"dish_id": 4, "options": [{"option_id": 1}]}, ctx)
    assert server.requests == [("POST", "/orders"), ("POST", "/orders/7/lines")]


def test_a_name_and_an_id_can_be_mixed() -> None:
    ctx, server, tools = setup()
    args = {"dish_id": 4, "options": [{"option_id": 1}, {"name": "Double Cheese", "qty": 2}]}
    assert tools.dispatch("add_to_order", args, ctx).ok
    assert server.sent["options"] == [{"option_id": 1, "qty": 1}, {"option_id": 5, "qty": 2}]


def test_case_and_symbols_do_not_matter_and_neither_does_a_missing_last_word() -> None:
    for name in ("mcaloo tikki burger ®", "McAloo Tikki Burger", "McAloo Tikki"):
        ctx, server, tools = setup()
        assert tools.dispatch("add_to_order", {"dish": name}, ctx).ok, name
        assert server.sent["product_id"] == 4


def test_meal_choices_are_found_with_the_meal_size() -> None:
    ctx, server, tools = setup()
    args = {
        "dish": "McAloo Tikki Burger",
        "meal_size": "Large",
        "options": [{"name": "No Ketchup"}, {"name": "Large Coke"}],
    }
    assert tools.dispatch("add_to_order", args, ctx).ok
    assert server.sent["meal_size"] == "Large"
    assert server.sent["options"] == [{"option_id": 2, "qty": 1}, {"option_id": 40, "qty": 1}]


def test_an_unknown_dish_adds_nothing_and_offers_the_nearest_names() -> None:
    ctx, server, tools = setup()
    result = tools.dispatch("add_to_order", {"dish": "Big Mac"}, ctx)
    assert not result.ok and result.error is not None
    assert result.error.code == "unknown_dish"
    assert "Big Mac" in result.error.message
    assert result.error.hint == "None are close"
    near = tools.dispatch("add_to_order", {"dish": "Spicy Burger"}, ctx)
    assert near.error is not None and near.error.hint == "Closest: McAloo Tikki Burger"
    assert ("POST", "/orders") not in server.requests  # no empty draft was started
    assert ctx.order.order_id is None and not result.changed


def test_a_choice_that_fits_several_is_never_guessed() -> None:
    ctx, server, tools = setup()
    args = {"dish": "McAloo Tikki Burger", "meal_size": "Medium", "options": [{"name": "Coke"}]}
    result = tools.dispatch("add_to_order", args, ctx)
    assert result.error is not None and result.error.code == "ambiguous_option"
    assert result.error.hint == (
        "Ask the customer which one: Medium Coke, Coke Zero, Coke Zero Can"
    )
    assert server.sent == {} and ctx.order.order_id is None


def test_the_whole_name_wins_over_a_longer_name_that_contains_it() -> None:
    ctx, server, tools = setup()
    args = {"dish_id": 4, "options": [{"name": "Cheese"}, {"name": "ketchup"}]}
    result = tools.dispatch("add_to_order", args, ctx)
    assert result.error is not None and result.error.code == "ambiguous_option"
    assert "Complimentary Ketchup" in result.error.hint and "No Ketchup" in result.error.hint


def test_a_meal_choice_without_its_meal_size_says_which_to_send() -> None:
    ctx, _, tools = setup()
    args = {"dish_id": 4, "options": [{"name": "Large Coke"}]}
    result = tools.dispatch("add_to_order", args, ctx)
    assert result.error is not None and result.error.code == "needs_meal_size"
    assert result.error.message == "'Large Coke' is a choice of the Large meal"
    assert result.error.hint == 'Send meal_size "Large" with it'


def test_a_choice_of_the_other_meal_size_says_so() -> None:
    ctx, _, tools = setup()
    args = {"dish_id": 4, "meal_size": "Medium", "options": [{"name": "Large Coke"}]}
    result = tools.dispatch("add_to_order", args, ctx)
    assert result.error is not None and result.error.code == "wrong_meal_size"
    assert result.error.message == "'Large Coke' is a choice of the Large meal, not the Medium meal"


def test_an_unknown_choice_lists_what_is_close_on_that_dish() -> None:
    ctx, _, tools = setup()
    result = tools.dispatch("add_to_order", {"dish_id": 4, "options": [{"name": "Jalapeno"}]}, ctx)
    assert result.error is not None and result.error.code == "unknown_option"
    assert result.error.message == "No option called 'Jalapeno' on McAloo Tikki Burger"


def test_an_item_needs_a_name_or_an_id_and_a_choice_needs_a_name_or_an_id() -> None:
    ctx, _, tools = setup()
    for args in (
        {},
        {"dish": "McAloo Tikki Burger", "dish_id": 4},
        {"dish_id": 4, "options": [{}]},
        {"dish_id": 4, "options": [{"name": "Cheese", "option_id": 4}]},
    ):
        result = tools.dispatch("add_to_order", args, ctx)
        assert result.error is not None and result.error.code == "invalid_arguments", args


def test_the_summary_line_names_the_item_when_it_was_not_added() -> None:
    ctx, _, tools = setup()
    args = {"dish": "Big Mac"}
    refused = tools.dispatch("add_to_order", args, ctx)
    assert tools.compact("add_to_order", args, refused) == "'Big Mac': not added (unknown_dish)"


# --- what the model is told when the server refuses


def test_an_unanswered_question_comes_back_with_its_options() -> None:
    ctx, _, tools = setup()
    result = tools.dispatch("add_to_order", {"dish_id": 5}, ctx)
    assert result.error is not None
    assert result.error.hint == (
        "Nothing was added. Ask the customer: Sauce: Tomato Ketchup, No Sauce."
    )


def test_a_dish_with_many_options_says_how_many_and_how_to_open_them() -> None:
    ctx, _, tools = setup()
    result = tools.dispatch("add_to_order", {"dish_id": 6}, ctx)  # Float: 10 flavours
    assert result.error is not None and result.error.code == "incomplete"
    assert "Flavour: 10 options, open it with get_item question" in (result.error.hint or "")


def test_names_in_the_reply_are_cleaned_like_the_menu() -> None:
    ctx, server, tools = setup()
    server.next_name = "McAloo Tikki Burger ®"
    result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.data["added"]["name"] == "McAloo Tikki Burger"  # no ®, as get_menu will say it


def test_an_item_that_is_off_the_menu_says_so_without_the_ids() -> None:
    ctx, server, tools = setup()
    server.refuse_add = ("unavailable", "McAloo Tikki is not available at this outlet")
    result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.error is not None and result.error.code == "unavailable"
    assert result.error.message == "McAloo Tikki is not available at this outlet"
    assert not result.changed


def test_a_wrong_choice_is_invalid_choice() -> None:
    ctx, server, tools = setup()
    server.refuse_add = ("too_many", "McAloo Tikki: Sauce allows at most 1, got 2")
    result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.error is not None and result.error.code == "invalid_choice"


# --- a dropped connection must not add the item twice


def test_a_lost_reply_is_not_added_twice() -> None:
    ctx, server, tools = setup()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.lose_next_reply = True  # the server adds the item, the reply never comes back
    result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.ok and len(server.lines) == 2
    assert result.data["added"]["line_id"] == 11 and result.data["line_count"] == 2
    assert server.requests.count(("POST", "/orders/7/lines")) == 2  # not retried


def test_a_request_that_never_arrived_is_sent_again() -> None:
    ctx, server, tools = setup()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    real = server._serve

    def drop_first(request):  # the add is lost on the way: nothing reaches the server
        if request.method == "POST" and request.url.path.endswith("/lines") and not drop_first.done:
            drop_first.done = True
            raise httpx.ReadTimeout("lost", request=request)
        return real(request)

    drop_first.done = False
    server._serve = drop_first
    result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.ok and len(server.lines) == 2  # added exactly once
