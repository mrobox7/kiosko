"""The supervisor graph: matching, routing, and whole turns with a scripted model, the real tools
and the fake ordering server."""

import json
from typing import Any

import pytest

from app.agent.context import FALLBACK
from app.agent.graph import build_graph, make_saver
from app.agent.items import Item
from app.agent.nodes.respond import CLOSING
from app.agent.nodes.searcher import NOT_FOUND
from app.agent.router import next_step, runnable
from app.agent.services import Services
from app.agent.utils.classify_item import classify_item
from app.backend.models import Dish, Line, Order
from app.llm.contract import LLMError, LLMResponse
from app.llm.messages import ToolCall
from tests.support.builders import OUTLET_INFO, clock, make_ctx, say
from tests.support.fake_llm import FakeLLM
from tests.support.fake_order_server import FakeOrderServer


def dish(i: int, name: str) -> Dish:
    return Dish(id=i, name=name, kind="item", veg="veg", category="x", base_price=1)


DISHES = [
    dish(1, "McAloo Tikki Burger ®"),
    dish(2, "Chicken McNuggets® 6pc"),
    dish(3, "Chicken McNuggets® 20pc"),
    dish(4, "Coke"),
]


def item(kind: str = "add", text: str | None = None, **more: Any) -> Item:
    return Item(id="1.1", kind=kind, dish_text=text, **more)  # type: ignore[arg-type]


def order_with(*line_ids: int) -> Order:
    lines = [Line(id=i, name="McAloo Tikki Burger", quantity=1, line_total=1) for i in line_ids]
    return Order(id=1, status="draft", lines=lines, subtotal=1, gst=0, total=1)


# --- matching


def test_a_whole_name_is_ready_with_its_id() -> None:
    got = classify_item(item(text="mcaloo tikki burger"), DISHES, None)
    assert (got.status, got.dish_id) == ("ready", 1)


def test_a_phrase_that_fits_several_dishes_asks_with_their_names() -> None:
    got = classify_item(item(text="chicken mcnuggets"), DISHES, None)
    assert got.status == "needs_user"
    assert got.candidates == ["Chicken McNuggets 6pc", "Chicken McNuggets 20pc"]


def test_several_dishes_of_one_kind_are_offered_as_options() -> None:
    two = [dish(1, "McAloo Tikki Burger ®"), dish(2, "Veg-Surprise Burger"), dish(3, "Coke")]
    got = classify_item(item(text="burger"), two, None)
    assert got.question == (
        "We have a few burger options: McAloo Tikki Burger or Veg-Surprise Burger. "
        "Which one would you like?"
    )


def test_a_near_miss_asks_do_you_mean() -> None:
    got = classify_item(item(text="diet coke"), DISHES, None)
    assert got.status == "needs_user" and got.question == "Do you mean Coke?"


def test_spoken_words_find_the_dish_without_a_search() -> None:
    menu = [dish(1, "McAloo Tikki Burger ®"), dish(2, "Happy Meal McAloo Tikki Burger*")]
    menu[1] = menu[1].model_copy(update={"kind": "combo"})
    got = classify_item(item(text="mc aloo tikki"), menu, None)
    assert (got.status, got.dish_id) == ("ready", 1)


def test_words_that_fit_nothing_go_to_the_searcher() -> None:
    assert classify_item(item(text="a drink"), DISHES, None).status == "needs_search"
    assert classify_item(item(text=None), DISHES, None).status == "needs_user"


def test_search_chat_place_and_cancel_need_no_matching() -> None:
    kinds = ["search", "chat", "place", "cancel"]
    got = [classify_item(item(k, "x"), DISHES, None).status for k in kinds]
    assert got == ["needs_search", "done", "ready", "ready"]


def test_choices_are_matched_against_the_dish_s_own_questions() -> None:
    menu = make_ctx().menu.dishes
    ok = classify_item(item(text="mcaloo tikki burger", options=["no ketchup"]), menu, None)
    assert (ok.status, ok.option_ids) == ("ready", [2])
    odd = classify_item(item(text="mcaloo tikki burger", options=["pickles"]), menu, None)
    assert odd.status == "needs_user" and "pickles" in (odd.question or "")


def test_a_line_must_be_on_the_order() -> None:
    order = order_with(7)
    assert classify_item(item("remove", target_line=7), DISHES, order).status == "ready"
    gone = classify_item(item("remove", target_line=9), DISHES, order)
    assert gone.status == "needs_user" and gone.candidates == ["line 7: McAloo Tikki Burger"]
    by_name = classify_item(item("change_qty", "tikki burger", qty=2), DISHES, order)
    assert (by_name.status, by_name.target_line) == ("ready", 7)


# --- router


def test_the_router_reads_statuses() -> None:
    def step(*pairs: tuple[str, str]) -> str:
        return next_step([item(kind, status=status) for kind, status in pairs])  # type: ignore[arg-type]

    assert step(("add", "needs_search"), ("add", "ready")) == "searcher"
    assert step(("add", "needs_user"), ("add", "ready")) == "executor"  # run what is clear
    assert step(("add", "needs_user")) == "respond"
    assert step(("add", "ready"), ("search", "done")) == "executor"
    assert step(("chat", "done")) == "respond"
    assert step() == "respond"


def test_place_and_cancel_wait_while_anything_else_is_unresolved() -> None:
    def runs(*pairs: tuple[str, str]) -> list[str]:
        return [i.kind for i in runnable([item(k, status=st) for k, st in pairs])]  # type: ignore[arg-type]

    assert runs(("add", "ready"), ("place", "ready")) == ["add", "place"]
    assert runs(("add", "ready"), ("add", "needs_user"), ("place", "ready")) == ["add"]
    assert runs(("add", "needs_search"), ("cancel", "ready")) == []


# --- whole turns


def chat(script: list[Any]) -> tuple[Any, FakeLLM, dict[str, Any], FakeOrderServer]:
    server = FakeOrderServer()
    ctx = make_ctx(server)
    llm = FakeLLM(script)
    services = Services(
        backend=ctx.backend, menu=ctx.menu, llm=llm, clock=clock, outlet=OUTLET_INFO
    )
    graph = build_graph(services, make_saver())
    return graph, llm, {"configurable": {"thread_id": "chat-1"}}, server


def send(graph: Any, config: dict[str, Any], text: str, **context: Any) -> dict[str, Any]:
    return graph.invoke({"user_text": text}, config, context=context)


def _call(name: str, arguments: dict[str, Any]) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"call-{name}", name=name, arguments=arguments)])


def understood(
    *items: dict[str, Any], updates: list[dict[str, Any]] | None = None, **top: Any
) -> LLMResponse:
    body = {"language": "en", "items": list(items), "updates": updates or [], **top}
    return _call("record_request", body)


def found(answer: str, *candidates: str, available: bool = True) -> LLMResponse:
    body = {"answer": answer, "candidates": list(candidates), "available": available}
    return _call("finish", body)


def tool(name: str, **args: Any) -> LLMResponse:
    return _call(name, args)


TIKKI = {"kind": "add", "dish_text": "McAloo Tikki Burger"}


def test_a_chat_turn_is_one_model_call() -> None:
    graph, llm, config, _ = chat([understood({"kind": "chat"}, reply="Hello! What can I get you?")])
    out = send(graph, config, "hi")
    assert out["reply"] == "Hello! What can I get you?" and len(llm.calls) == 1


def test_a_dish_is_matched_in_code_added_and_the_reply_written_from_the_result() -> None:
    graph, llm, config, _ = chat([understood(TIKKI), say("One McAloo Tikki added.")])
    out = send(graph, config, "a tikki burger")
    assert [ln.quantity for ln in out["order"].lines] == [1]
    # the words are the model's; the summary after them is built by code from the real order
    assert (
        out["reply"]
        == "One McAloo Tikki added.\nYour order:\n1 × McAloo Tikki\nTotal ₹80.00\n" + CLOSING
    )
    assert out["items"] == []
    assert len(llm.calls) == 2  # supervisor, respond: no search, so no searcher call
    shown = llm.calls[1].messages[-2].text or ""
    assert "DONE: added McAloo Tikki." in shown and "80" not in shown  # no price is shown


def test_the_clear_item_is_added_now_and_the_unclear_one_is_asked_then_added() -> None:
    drink = {"kind": "add", "dish_text": "a drink"}
    graph, llm, config, _ = chat(
        [
            understood(drink, TIKKI),
            found("Did you mean the Float?", "Float", "Not On The Menu"),
            say("Tikki added. Do you want the Float?"),
            understood(updates=[{"id": "1.1", "dish_text": "float"}]),
            say("Which flavour for the Float?"),
            understood(updates=[{"id": "1.1", "options": ["Cola Float"]}]),
            say("Float added."),
        ]
    )
    out = send(graph, config, "a drink and a tikki burger")
    assert len(out["order"].lines) == 1  # the tikki is in already
    assert [(i.dish_text, i.status) for i in out["items"]] == [("a drink", "needs_user")]
    assert out["items"][0].candidates == ["Float"]  # a name not on the menu is dropped
    assert len(llm.calls) == 3  # supervisor, search, reply; the executor makes no call

    out = send(graph, config, "the float")  # clear now, but the Float has a flavour to choose
    assert len(out["order"].lines) == 1
    assert [(i.dish_text, i.status) for i in out["items"]] == [("float", "needs_user")]

    out = send(graph, config, "cola float")
    assert len(out["order"].lines) == 2 and out["items"] == []


def test_a_menu_question_runs_the_tools_and_does_not_block_an_add() -> None:
    ask = {"kind": "search", "dish_text": "what burgers do you have"}
    graph, llm, config, _ = chat(
        [
            understood(ask, TIKKI),
            tool("get_menu", category="burgers"),
            found("McAloo Tikki Burger and McSpicy Chicken."),
            say("We have the Tikki and McSpicy. I added a Tikki."),
        ]
    )
    out = send(graph, config, "what burgers do you have, and add a tikki")
    assert len(out["order"].lines) == 1
    assert "McSpicy" in llm.calls[2].messages[-1].tool_outcomes[0].content  # tool result fed back
    assert "McSpicy Chicken." in llm.calls[3].messages[-2].text  # type: ignore[operator]


def test_a_searcher_that_keeps_calling_tools_is_stopped_and_the_customer_is_asked() -> None:
    again = tool("get_menu", category="beverages")
    graph, llm, config, _ = chat(
        [understood({"kind": "add", "dish_text": "a drink"}), again, again, again]
    )
    out = send(graph, config, "a drink")
    assert out["items"][0].question == NOT_FOUND and out.get("order") is None
    assert len(llm.calls) == 4  # one supervisor, three searcher calls; code puts the question


def test_a_line_is_removed_by_the_name_the_customer_gives() -> None:
    graph, _, config, _ = chat(
        [
            understood(TIKKI),
            say("Added."),
            understood({"kind": "remove", "dish_text": "tikki"}),
            say("Removed."),
        ]
    )
    assert len(send(graph, config, "a tikki")["order"].lines) == 1
    assert send(graph, config, "remove it")["order"].lines == []


def test_unreadable_model_output_is_retried_once_then_asks_again() -> None:
    graph, llm, config, _ = chat([LLMResponse(text="sure!"), LLMResponse(text="{not json")])
    out = send(graph, config, "a tikki")
    assert out["reply"] == FALLBACK["unclear"] and out["stop_reason"] == "unclear"
    assert len(llm.calls) == 2


def test_an_unreachable_model_ends_the_turn_politely() -> None:
    graph, _, config, _ = chat([LLMError("down")])
    out = send(graph, config, "a tikki")
    assert out["reply"] == FALLBACK["llm_error"] and out["stop_reason"] == "llm_error"


def test_the_reply_streams_to_the_caller() -> None:
    graph, _, config, _ = chat([understood(TIKKI), say("One tikki added.")])
    words: list[str] = []
    out = send(graph, config, "a tikki", on_text=words.append)
    assert "".join(words) == out["reply"]  # the summary is streamed after the words too
    assert (
        out["reply"].startswith("One tikki added.\nYour order:") and "Total ₹80.00" in out["reply"]
    )


def test_a_remove_of_a_line_that_is_not_there_asks_and_the_rest_still_runs() -> None:
    graph, _, config, _ = chat(
        [
            understood({"kind": "remove", "target_line": 1}, TIKKI),
            say("I couldn't find that line, but the tikki is in."),
        ]
    )
    out = send(graph, config, "remove line 1 and add a tikki")
    assert len(out["order"].lines) == 1
    assert [i.status for i in out["items"]] == ["needs_user"]


def test_a_second_turn_starts_clean_and_keeps_the_history() -> None:
    graph, _, config, _ = chat(
        [understood({"kind": "chat"}, reply="Hi!"), understood({"kind": "chat"}, reply="Bye!")]
    )
    send(graph, config, "hi")
    assert send(graph, config, "bye")["reply"] == "Bye!"
    assert len(graph.get_state(config).values["history"]) == 2


# --- native tool calling


def test_supervisor_must_answer_with_the_one_record_tool_in_a_plain_schema() -> None:
    graph, llm, config, _ = chat([understood({"kind": "chat"}, reply="Hi!")])
    send(graph, config, "hi")
    call = llm.calls[0]
    assert call.require_tool and [t.name for t in call.tools] == ["record_request"]
    schema = json.dumps(call.tools[0].parameters)
    assert "$ref" not in schema and "$defs" not in schema and '"title"' not in schema
    assert "add" in schema and "status" not in schema  # what the model writes, not what code sets


def test_the_searcher_gets_the_menu_tools_and_answers_every_call_it_makes() -> None:
    both = LLMResponse(
        tool_calls=[
            ToolCall(id="a", name="get_menu", arguments={"category": "burgers"}),
            ToolCall(id="b", name="get_item", arguments={"dish": "Float"}),
        ]
    )
    graph, llm, config, _ = chat(
        [
            understood({"kind": "search", "dish_text": "burgers"}),
            both,
            found("Tikki and McSpicy."),
            say("We have the Tikki and McSpicy."),
        ]
    )
    send(graph, config, "burgers?")
    first = llm.calls[1]
    assert {t.name for t in first.tools} == {"get_menu", "get_item", "finish"}
    assert first.require_tool
    after = llm.calls[2].messages  # the question, the assistant's calls, then one answer for each
    assert [c.id for c in after[1].tool_calls] == ["a", "b"]
    assert [o.call_id for o in after[2].tool_outcomes] == ["a", "b"]


def test_the_last_search_round_offers_only_finish() -> None:
    again = tool("get_menu", category="burgers")
    graph, llm, config, _ = chat(
        [
            understood({"kind": "add", "dish_text": "a drink"}),
            again,
            again,
            found("Which?"),
            say("?"),
        ]
    )
    send(graph, config, "a drink")
    assert [t.name for t in llm.calls[3].tools] == ["finish"]


def test_a_finish_with_bad_arguments_is_answered_and_the_searcher_tries_again() -> None:
    bad = _call("finish", {"candidates": "Float"})  # no answer, and not a list
    graph, llm, config, _ = chat(
        [
            understood({"kind": "add", "dish_text": "a drink"}),
            bad,
            found("Did you mean the Float?", "Float"),
            say("Float?"),
        ]
    )
    out = send(graph, config, "a drink")
    assert out["items"][0].candidates == ["Float"]
    retried = llm.calls[2].messages[-1].tool_outcomes[0]
    assert retried.call_id == "call-finish" and "error" in retried.content


def test_a_reply_in_plain_text_where_the_tool_was_required_is_not_accepted() -> None:
    graph, llm, config, _ = chat(
        [LLMResponse(text='{"items": []}'), understood({"kind": "chat"}, reply="Hi!")]
    )
    out = send(graph, config, "hi")
    assert out["reply"] == "Hi!" and len(llm.calls) == 2  # retried once, then understood


def test_place_is_not_run_while_a_question_is_open_and_is_not_kept() -> None:
    graph, llm, config, _ = chat(
        [
            understood({"kind": "add", "dish_text": "a drink"}, TIKKI, {"kind": "place"}),
            found("Which drink?", "Float"),
            say("Tikki added. Which drink? Say when you want to place the order."),
        ]
    )
    out = send(graph, config, "a drink, a tikki, and place it")
    assert len(out["order"].lines) == 1 and out["order"].status == "draft"  # not placed
    assert [i.kind for i in out["items"]] == ["add"]  # only the question is kept
    shown = llm.calls[-1].messages[-2].text or ""
    assert "NOT DONE: placing the order has not happened yet" in shown


def test_a_dish_that_is_not_on_the_menu_is_reported_with_alternatives_and_blocks_nothing() -> None:
    graph, llm, config, _ = chat(
        [
            understood({"kind": "add", "dish_text": "pizza"}, TIKKI),
            _call(
                "finish",
                {"answer": "No pizza.", "candidates": ["McSpicy Chicken"], "available": False},
            ),
            say("Tikki added. No pizza, but we have the McSpicy Chicken."),
        ]
    )
    out = send(graph, config, "pizza and a tikki")
    assert len(out["order"].lines) == 1 and out["items"] == []  # nothing left open
    shown = llm.calls[-1].messages[-2].text or ""
    assert "NOT SOLD: pizza is not on the menu. Close dishes: McSpicy Chicken." in shown


def test_only_supervisor_gets_the_menu_card_the_searcher_must_look() -> None:
    ask = {"kind": "search", "dish_text": "pizza"}
    graph, llm, config, _ = chat(
        [understood(ask), found("No pizza.", available=False), say("No pizza.")]
    )
    send(graph, config, "do you have pizza?")
    supervisor_call, search_call = llm.calls[:2]
    assert "Burgers [burgers]: veg + non-veg - McAloo Tikki" in supervisor_call.system
    assert "Burgers [burgers]" not in search_call.system and "McAloo" not in search_call.system


def test_the_saved_state_reads_back_with_its_trace_events(caplog: pytest.LogCaptureFixture) -> None:
    graph, _, config, _ = chat([understood(TIKKI), say("Added.")])
    send(graph, config, "a tikki burger")
    saved = graph.get_state(config).values  # what the session reads between turns
    assert [type(e).__name__ for e in saved["events"]][0] == "GuardDecided"
    assert "Blocked deserialization" not in caplog.text


def test_a_lookup_that_cannot_run_reaches_the_reply_as_a_technical_problem() -> None:
    ask = {"kind": "search", "dish_text": "pizza"}
    graph, llm, config, _ = chat([understood(ask), LLMError("down"), say("Sorry, try again.")])
    send(graph, config, "do you have pizza?")
    shown = llm.calls[-1].messages[-2].text or ""
    assert "FAILED: a technical problem stopped the menu lookup" in shown
    assert "unavailable" not in shown and "NOT SOLD" not in shown  # a failure is not "not sold"


def test_a_show_order_turn_has_the_order_read_back_by_code() -> None:
    graph, _, config, _ = chat(
        [
            understood({**TIKKI, "qty": 2}),
            say("Added."),
            understood({"kind": "show_order"}),
            say("Here is your order."),
        ]
    )
    send(graph, config, "two tikki burgers")
    out = send(graph, config, "that's all")
    assert (
        out["reply"]
        == "Here is your order.\nYour order:\n2 × McAloo Tikki\nTotal ₹160.00\n" + CLOSING
    )


def test_a_size_given_for_a_dish_without_a_meal_is_taken_as_a_choice() -> None:
    dish = Dish.model_validate(
        {
            "id": 53, "name": "Coke", "kind": "item", "veg": "veg", "category": "drinks",
            "base_price": 84.76, "meal_offers": [],
            "option_groups": [
                {
                    "id": 26, "name": "Size", "min_select": 1, "max_select": 1,
                    "options": [
                        {"id": 40, "name": "Small", "price_delta": 0, "is_default": False},
                        {"id": 41, "name": "Medium", "price_delta": 13.34, "is_default": False},
                    ],
                }
            ],
        }
    )  # fmt: skip
    asked = Item(kind="add", dish_text="coke", meal_size="Medium", id="1")
    got = classify_item(asked, [dish], None)
    assert got.status == "ready" and got.option_ids == [41] and got.meal_size is None
