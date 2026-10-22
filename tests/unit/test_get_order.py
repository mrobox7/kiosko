"""get_order: the order read back from what the chat already holds."""

from tests.support.builders import make_order_tools


def test_an_empty_chat_says_the_order_is_empty_without_a_request() -> None:
    ctx, server, tools = make_order_tools()
    result = tools.dispatch("get_order", {}, ctx)
    assert result.ok and result.data == {"lines": [], "note": "The order is empty."}
    assert server.requests == [] and not result.changed
    assert tools.compact("get_order", {}, result) == "order: empty"


def test_every_line_and_the_totals_are_read_back_with_no_request() -> None:
    ctx, server, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4, "quantity": 2, "note": "no onions"}, ctx)
    tools.dispatch("add_to_order", {"dish_id": 5, "options": [{"option_id": 7}]}, ctx)
    server.requests.clear()
    result = tools.dispatch("get_order", {}, ctx)
    assert result.data["order_id"] == 7
    assert [x["line_id"] for x in result.data["lines"]] == [10, 11]
    assert result.data["lines"][0] == {
        "line_id": 10,
        "name": "McAloo Tikki",
        "quantity": 2,
        "line_total": 152.38,
        "note": "no onions",
    }
    assert (result.data["subtotal"], result.data["gst"], result.data["total"]) == (
        416.19, 20.81, 437.0
    )  # fmt: skip
    assert server.requests == []
    assert tools.compact("get_order", {}, result) == "order 7: 2 lines, total 437.0"


def test_a_draft_emptied_by_removals_reads_as_empty() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("remove_from_order", {"line_id": 10}, ctx)
    assert tools.dispatch("get_order", {}, ctx).data["note"] == "The order is empty."
