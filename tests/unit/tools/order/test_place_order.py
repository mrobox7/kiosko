"""place_order against a stand-in for the ordering server."""

from tests.support.builders import make_order_tools


def test_placing_the_order_returns_its_number_and_totals() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4, "quantity": 2}, ctx)
    result = tools.dispatch("place_order", {}, ctx)
    assert result.ok
    assert result.data["order_number"] == 14 and result.data["order_id"] == 7
    assert [(x["line_id"], x["name"], x["quantity"]) for x in result.data["lines"]] == [
        (10, "McAloo Tikki", 2)
    ]
    assert (result.data["subtotal"], result.data["gst"], result.data["total"]) == (
        152.38, 7.62, 160.0
    )  # fmt: skip
    assert server.requests[-1] == ("POST", "/orders/7/confirm")
    assert result.changed


def test_after_placing_the_chat_holds_the_placed_order_and_will_not_place_it_again() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("place_order", {}, ctx)
    assert ctx.placed and ctx.order is not None
    assert ctx.order.order_number == 14
    server.requests.clear()
    again = tools.dispatch("place_order", {}, ctx)
    assert not again.ok and again.error is not None and again.error.code == "already_placed"
    assert "number 14" in again.error.message and server.requests == []  # no request


def test_with_no_order_yet_it_says_so_without_calling_the_server() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("place_order", {}, ctx)
    assert not result.ok and result.error is not None and result.error.code == "no_order"
    assert server.requests == []


def test_an_empty_order_is_refused_and_stays_open() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("remove_from_order", {"line_id": 10}, ctx)
    result = tools.dispatch("place_order", {}, ctx)
    assert not result.ok and result.error is not None
    assert "empty" in result.error.message and ctx.order.id == 7


def test_a_price_change_is_reported_and_the_order_stays_open_to_try_again() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.price_changed = True
    result = tools.dispatch("place_order", {}, ctx)
    assert not result.ok and result.error is not None
    assert "McAloo Tikki is now 80" in result.error.message and not result.changed
    assert ctx.order.id == 7
    server.price_changed = False
    assert tools.dispatch("place_order", {}, ctx).ok


def test_a_price_change_shows_the_new_prices_and_the_new_total() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.price_changed = True
    result = tools.dispatch("place_order", {}, ctx)
    assert result.error is not None and result.error.code == "price_changed"
    assert "total now 90.5" in (result.error.hint or "")  # 76.19 + 10, plus 5% GST
    assert ctx.order is not None and ctx.order.lines[0].line_total == 86.19
    assert not ctx.placed


def test_an_order_finished_behind_the_chats_back_is_shown_as_it_is() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.status = "cancelled"  # e.g. the till cancelled it
    result = tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert result.error is not None and result.error.code == "order_closed"
    assert ctx.order is not None and ctx.order.status == "cancelled"


def test_a_lost_reply_does_not_place_the_order_twice() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    server.lose_next_reply = True  # the server placed it, the answer never came back
    result = tools.dispatch("place_order", {}, ctx)
    assert result.ok and result.data["order_number"] == 14 and ctx.placed
    assert server.requests.count(("POST", "/orders/7/confirm")) == 1
