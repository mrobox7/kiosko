"""set_customer: recognising the customer by the mobile number they offered."""

from tests.support.builders import make_order_tools

ASK = {"phone": "98765 43210", "digits_confirmed": True}


def test_a_known_customer_brings_back_allergies_and_usual_dishes() -> None:
    ctx, server, tools = make_order_tools()
    server.preferences = {"allergies": ["milk"]}
    server.favourites = [
        {"product_id": 5, "name": "McSpicy Chicken ®", "times_ordered": 4, "total_quantity": 6,
         "last_ordered_at": "2030-05-30T12:00:00Z"},
    ]  # fmt: skip
    result = tools.dispatch("set_customer", ASK, ctx)
    assert result.ok and result.changed
    assert result.data == {
        "identified": True,
        "allergies": ["milk"],
        "usual_dishes": ["McSpicy Chicken"],
    }
    assert ctx.customer_id == 3 and ctx.caller.usual == ["McSpicy Chicken"]
    assert "98765" not in str(result.data)  # the number is never echoed back


def test_a_new_customer_needs_nothing_else_and_ordering_goes_on() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("set_customer", ASK, ctx)
    assert result.ok and result.data == {"identified": True}
    assert ("GET", "/customers/3/favourites") in server.requests
    assert tools.dispatch("add_to_order", {"dish_id": 4}, ctx).ok
    assert server.created_with == {"outlet": "JPR-013-7429", "customer_id": 3}


def test_an_order_already_started_is_put_on_the_customer() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert server.customer_id is None
    tools.dispatch("set_customer", ASK, ctx)
    assert server.customer_id == 3 and ("PUT", "/orders/7/customer") in server.requests
    assert ctx.order.latest is not None and ctx.order.latest.customer_id == 3
    assert len(server.lines) == 1  # nothing on the order was lost


def test_the_customer_must_have_confirmed_the_digits() -> None:
    ctx, server, tools = make_order_tools()
    for args in ({"phone": ASK["phone"]}, {**ASK, "digits_confirmed": False}):
        result = tools.dispatch("set_customer", args, ctx)
        assert result.error is not None and result.error.code == "invalid_arguments"
    assert server.requests == [] and ctx.customer_id is None


def test_a_number_that_is_not_a_mobile_is_refused_and_nobody_is_set() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("set_customer", {"phone": "12345 67890", "digits_confirmed": True}, ctx)
    assert result.error is not None and result.error.code == "invalid_phone"
    assert "ten digits" in (result.error.hint or "")
    assert ctx.customer_id is None and not result.changed


def test_the_usual_dishes_failing_to_load_does_not_stop_the_customer_being_set() -> None:
    ctx, server, tools = make_order_tools()
    real = server._serve

    def favourites_down(request):
        if request.url.path.endswith("/favourites"):
            import httpx

            return httpx.Response(500, text="down")
        return real(request)

    server._serve = favourites_down
    result = tools.dispatch("set_customer", ASK, ctx)
    assert result.ok and ctx.customer_id == 3 and ctx.caller.usual == []


def test_a_lost_reply_just_looks_the_customer_up_again() -> None:
    ctx, server, tools = make_order_tools()
    server.lose_next_reply = True
    result = tools.dispatch("set_customer", ASK, ctx)
    assert result.ok and ctx.customer_id == 3
    assert server.requests.count(("POST", "/customers")) == 2


def test_the_summary_line_never_holds_the_number() -> None:
    ctx, server, tools = make_order_tools()
    server.favourites = [
        {"product_id": 4, "name": "McAloo Tikki Burger ®", "times_ordered": 2, "total_quantity": 2,
         "last_ordered_at": "2030-05-30T12:00:00Z"},
    ]  # fmt: skip
    done = tools.dispatch("set_customer", ASK, ctx)
    line = tools.compact("set_customer", ASK, done)
    assert line == "customer identified, usually McAloo Tikki Burger" and "9876" not in line
    bad = tools.dispatch("set_customer", {"phone": "1" * 10, "digits_confirmed": True}, ctx)
    assert tools.compact("set_customer", ASK, bad) == "customer: not set (invalid_phone)"
