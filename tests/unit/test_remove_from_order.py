"""remove_from_order against a stand-in for the ordering server."""

from tests.support.builders import make_order_tools


def two_lines():
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4, "quantity": 2}, ctx)  # line 10
    tools.dispatch("add_to_order", {"dish_id": 5, "options": [{"option_id": 7}]}, ctx)  # line 11
    return ctx, server, tools


def test_removing_a_line_names_it_and_shows_what_is_left() -> None:
    ctx, server, tools = two_lines()
    result = tools.dispatch("remove_from_order", {"line_id": 10}, ctx)
    assert result.ok and result.changed
    assert result.data["removed"] == {"line_id": 10, "name": "McAloo Tikki", "quantity": 2}
    assert [line["line_id"] for line in result.data["lines"]] == [11]
    assert (result.data["subtotal"], result.data["total"]) == (263.81, 277.0)
    assert [x["id"] for x in server.lines] == [11]
    assert server.requests[-1] == ("DELETE", "/orders/7/lines/10")


def test_a_line_can_be_named_instead_of_numbered() -> None:
    ctx, server, tools = two_lines()
    result = tools.dispatch("remove_from_order", {"dish": "mcspicy chicken"}, ctx)
    assert result.ok and result.data["removed"]["line_id"] == 11
    assert server.requests[-1] == ("DELETE", "/orders/7/lines/11")


def test_naming_a_line_costs_no_request_to_find_it() -> None:
    ctx, server, tools = two_lines()
    server.requests.clear()
    tools.dispatch("remove_from_order", {"dish": "McAloo Tikki"}, ctx)
    assert server.requests == [("DELETE", "/orders/7/lines/10")]


def test_the_same_dish_on_two_lines_is_never_guessed() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("add_to_order", {"dish_id": 4, "quantity": 3}, ctx)
    result = tools.dispatch("remove_from_order", {"dish": "McAloo Tikki"}, ctx)
    assert result.error is not None and result.error.code == "ambiguous_line"
    assert "line 10: 1 x McAloo Tikki" in (result.error.hint or "")
    assert "line 11: 3 x McAloo Tikki" in (result.error.hint or "")
    assert len(server.lines) == 2 and not result.changed


def test_removing_the_last_line_leaves_an_empty_order_that_the_next_add_reuses() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    result = tools.dispatch("remove_from_order", {"line_id": 10}, ctx)
    assert result.data["lines"] == [] and result.data["total"] == 0
    assert ctx.order.order_id == 7
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert server.requests.count(("POST", "/orders")) == 1


def test_a_line_that_is_not_on_the_order_lists_the_lines_that_are() -> None:
    ctx, server, tools = two_lines()
    server.requests.clear()
    result = tools.dispatch("remove_from_order", {"line_id": 99}, ctx)
    assert result.error is not None and result.error.code == "unknown_line"
    assert result.error.hint == "Lines on the order: 10 McAloo Tikki, 11 McSpicy Chicken"
    assert server.requests == [] and not result.changed  # settled from the chat's own copy


def test_a_dish_that_is_not_on_the_order_offers_the_nearest() -> None:
    ctx, _, tools = two_lines()
    result = tools.dispatch("remove_from_order", {"dish": "Tikki Wrap"}, ctx)
    assert result.error is not None and result.error.code == "unknown_line"
    assert "McAloo Tikki" in (result.error.hint or "")


def test_with_no_order_yet_it_says_so_without_calling_the_server() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("remove_from_order", {"line_id": 1}, ctx)
    assert not result.ok and result.error is not None and result.error.code == "no_order"
    assert server.requests == []


def test_the_model_must_send_a_name_or_a_number_not_both() -> None:
    ctx, _, tools = two_lines()
    both = tools.dispatch("remove_from_order", {"dish": "McAloo Tikki", "line_id": 10}, ctx)
    neither = tools.dispatch("remove_from_order", {}, ctx)
    assert both.error is not None and both.error.code == "invalid_arguments"
    assert neither.error is not None and neither.error.code == "invalid_arguments"


def test_a_lost_reply_does_not_remove_the_line_twice_or_fail() -> None:
    ctx, server, tools = two_lines()
    server.lose_next_reply = True  # the server removed it, the answer never came back
    result = tools.dispatch("remove_from_order", {"line_id": 10}, ctx)
    assert result.ok and [x["id"] for x in server.lines] == [11]
    assert server.requests.count(("DELETE", "/orders/7/lines/10")) == 1


def test_the_summary_line_names_the_line_and_the_new_total() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    args = {"line_id": 10}
    done = tools.dispatch("remove_from_order", args, ctx)
    assert tools.compact("remove_from_order", args, done) == (
        "order 7: removed 1x McAloo Tikki (line 10), total 0.0"
    )
    gone = tools.dispatch("remove_from_order", args, ctx)
    assert tools.compact("remove_from_order", args, gone) == ("line 10: not removed (unknown_line)")
