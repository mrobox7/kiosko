"""change_quantity against a stand-in for the ordering server."""

from tests.support.builders import make_order_tools


def test_the_line_keeps_its_id_and_the_totals_follow() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    result = tools.dispatch("change_quantity", {"line_id": 10, "quantity": 3}, ctx)
    assert result.ok and result.changed
    assert result.data["changed_line_id"] == 10
    assert result.data["lines"] == [
        {"line_id": 10, "name": "McAloo Tikki", "quantity": 3, "line_total": 228.57}
    ]
    assert result.data["total"] == 240.0
    assert server.requests[-1] == ("PATCH", "/orders/7/lines/10")
    assert ctx.order.latest is not None and ctx.order.latest.lines[0].quantity == 3


def test_a_line_can_be_named() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    result = tools.dispatch("change_quantity", {"dish": "mcaloo tikki", "quantity": 2}, ctx)
    assert result.ok and server.requests[-1] == ("PATCH", "/orders/7/lines/10")


def test_a_line_that_is_not_there_is_refused_without_a_request() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.requests.clear()
    result = tools.dispatch("change_quantity", {"line_id": 99, "quantity": 2}, ctx)
    assert result.error is not None and result.error.code == "unknown_line"
    assert server.requests == []


def test_zero_or_too_many_is_refused_before_anything_happens() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    for quantity in (0, 21):
        result = tools.dispatch("change_quantity", {"line_id": 10, "quantity": quantity}, ctx)
        assert result.error is not None and result.error.code == "invalid_arguments"
    assert server.lines[0]["quantity"] == 1


def test_with_no_order_yet_it_says_so() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("change_quantity", {"line_id": 10, "quantity": 2}, ctx)
    assert result.error is not None and result.error.code == "no_order"
    assert server.requests == []


def test_a_lost_reply_is_simply_sent_again() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.lose_next_reply = True
    result = tools.dispatch("change_quantity", {"line_id": 10, "quantity": 4}, ctx)
    assert result.ok and server.lines[0]["quantity"] == 4  # four, not eight
    assert server.requests.count(("PATCH", "/orders/7/lines/10")) == 2


def test_the_summary_line() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    args = {"line_id": 10, "quantity": 3}
    done = tools.dispatch("change_quantity", args, ctx)
    assert tools.compact("change_quantity", args, done) == (
        "order 7: line 10 McAloo Tikki now 3x, total 240.0"
    )
