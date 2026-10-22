"""cancel_order: start over."""

from tests.support.builders import make_order_tools


def test_the_order_is_cancelled_and_the_next_item_starts_a_new_one() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    result = tools.dispatch("cancel_order", {}, ctx)
    assert result.ok and result.changed
    assert result.data["cancelled_order_id"] == 7 and result.data["lines_removed"] == 2
    assert server.status == "cancelled" and ("DELETE", "/orders/7") in server.requests
    assert ctx.order.latest is None and not ctx.order.placed
    again = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert again.ok and server.requests.count(("POST", "/orders")) == 2
    assert len(tools.dispatch("get_order", {}, ctx).data["lines"]) == 1  # the old lines are gone


def test_with_no_order_there_is_nothing_to_cancel() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("cancel_order", {}, ctx)
    assert result.error is not None and result.error.code == "no_order"
    assert server.requests == []


def test_a_placed_order_cannot_be_cancelled() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("place_order", {}, ctx)
    server.requests.clear()
    result = tools.dispatch("cancel_order", {}, ctx)
    assert result.error is not None and result.error.code == "already_placed"
    assert "number 14" in result.error.message and server.requests == []
    assert ctx.order.placed


def test_a_lost_reply_is_simply_sent_again() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.lose_next_reply = True
    result = tools.dispatch("cancel_order", {}, ctx)
    assert result.ok and server.status == "cancelled" and ctx.order.latest is None


def test_it_is_marked_destructive_and_the_summary_says_how_much_went() -> None:
    ctx, _, tools = make_order_tools()
    assert tools._tools["cancel_order"].destructive is True
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    done = tools.dispatch("cancel_order", {}, ctx)
    assert tools.compact("cancel_order", {}, done) == "order 7 cancelled (1 lines removed)"
