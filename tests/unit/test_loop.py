import json

from app.agent.events import ToolRequested, ToolReturned, TurnEnded
from app.agent.loop import AgentLoop
from app.domain.messages import Message, ToolCall
from app.llm.base import LLMError, LLMResponse
from app.llm.fake import FakeLLM
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx, make_loop, make_order_tools

CTX = make_ctx()
HISTORY = [Message(role="user", text="veg burgers?")]


def make(steps, **kw):
    llm = FakeLLM(steps)
    loop = AgentLoop(
        llm,
        ToolRegistry.discover(),
        max_iterations=kw.get("max_iterations", 8),
        max_tool_calls=kw.get("max_tool_calls", 12),
        tool_result_max_chars=kw.get("max_chars", 4000),
    )
    return loop, llm


def call(id="c1", name="get_menu", **args):
    return LLMResponse(tool_calls=[ToolCall(id=id, name=name, arguments=args)])


def test_text_only() -> None:
    loop, _ = make([LLMResponse(text="Hello")])
    r = loop.run("sys", HISTORY, CTX)
    assert r.stop_reason == "answered" and r.text == "Hello"
    assert [m.role for m in r.new_messages] == ["assistant"]


def test_tool_call_then_text_pairs_outcomes_and_traces() -> None:
    loop, llm = make([call(category="burgers"), LLMResponse(text="Here you go")])
    events = []
    r = loop.run("sys", HISTORY, CTX, events.append)
    assert r.stop_reason == "answered"
    outcomes = r.new_messages[1].tool_outcomes
    assert [o.call_id for o in outcomes] == ["c1"] and not outcomes[0].is_error
    assert "McAloo Tikki" in outcomes[0].content
    # second model call saw the tool outcome
    assert llm.calls[1].messages[-1].tool_outcomes[0].call_id == "c1"
    kinds = [type(e) for e in events]
    assert ToolRequested in kinds and ToolReturned in kinds and kinds[-1] is TurnEnded


def test_iteration_cap() -> None:
    loop, _ = make([call(id=f"c{i}") for i in range(3)], max_iterations=3)
    r = loop.run("sys", HISTORY, CTX)
    assert r.stop_reason == "max_iterations" and len(r.new_messages) == 6


def test_tool_call_budget_still_pairs_every_call() -> None:
    many = LLMResponse(tool_calls=[ToolCall(id=f"c{i}", name="get_menu") for i in range(3)])
    loop, _ = make([many, LLMResponse(text="done")], max_tool_calls=1)
    r = loop.run("sys", HISTORY, CTX)
    outcomes = r.new_messages[1].tool_outcomes
    assert [o.is_error for o in outcomes] == [False, True, True]
    assert "tool_call_budget" in outcomes[1].content


def test_bad_tool_call_gives_error_outcome_model_can_see() -> None:
    loop, _ = make([call(name="nope"), LLMResponse(text="sorry")])
    r = loop.run("sys", HISTORY, CTX)
    assert r.new_messages[1].tool_outcomes[0].is_error and r.stop_reason == "answered"


def test_llm_error_and_truncation() -> None:
    loop, _ = make([LLMError("down")])
    assert loop.run("s", HISTORY, CTX).stop_reason == "llm_error"
    loop, _ = make([LLMResponse(text="cut", truncated=True)])
    assert loop.run("s", HISTORY, CTX).stop_reason == "truncated"


def test_a_reply_too_long_to_show_becomes_an_error_not_broken_json() -> None:
    loop, _ = make([call(), LLMResponse(text="ok")], max_chars=100)
    r = loop.run("s", HISTORY, CTX)
    outcome = r.new_messages[1].tool_outcomes[0]
    assert outcome.is_error and "result_too_long" in outcome.content
    assert "[result cut off]" not in outcome.content and len(outcome.content) < 300
    json.loads(outcome.content)  # whole, valid JSON


def test_a_write_whose_reply_is_too_long_still_says_it_happened() -> None:
    ctx, _, tools = make_order_tools()
    loop = AgentLoop(
        FakeLLM([call(name="add_to_order", dish_id=4), LLMResponse(text="ok")]),
        tools,
        max_iterations=4,
        max_tool_calls=4,
        tool_result_max_chars=30,
    )
    r = loop.run("s", HISTORY, ctx)
    outcome = r.new_messages[1].tool_outcomes[0]
    assert "The change was made" in outcome.content and "get_order" in outcome.content
    assert "McAloo Tikki" in outcome.compact  # the failed-turn report still names the change
    assert r.changes == [outcome.compact]


def test_listener_failure_is_swallowed() -> None:
    def bad(event) -> None:
        raise RuntimeError("listener")

    loop, _ = make([LLMResponse(text="ok")])
    assert loop.run("s", HISTORY, CTX, bad).stop_reason == "answered"


def test_llm_error_cause_is_in_the_trace() -> None:
    loop, _ = make([LLMError("Error code: 429 - rate limit reached", retryable=True)])
    events = []
    loop.run("s", HISTORY, CTX, events.append)
    ended = [e for e in events if isinstance(e, TurnEnded)][0]
    assert ended.stop_reason == "llm_error"
    assert "429" in ended.detail and "retryable=True" in ended.detail


def test_on_text_receives_the_reply_as_it_is_written() -> None:
    llm = FakeLLM([LLMResponse(text="Here you go.")])
    pieces: list[str] = []
    result = make_loop(llm).run("sys", HISTORY, CTX, on_text=pieces.append)
    assert pieces == ["Here ", "you ", "go."] and result.text == "Here you go."


def test_without_on_text_the_plain_call_is_used() -> None:
    llm = FakeLLM([LLMResponse(text="Hi.")])
    llm.complete_stream = None  # type: ignore[method-assign,assignment]
    assert make_loop(llm).run("sys", HISTORY, CTX).text == "Hi."


def test_only_the_final_answer_is_streamed_on_a_tool_turn() -> None:
    steps = [
        LLMResponse(tool_calls=[ToolCall(id="c1", name="get_menu", arguments={})]),
        LLMResponse(text="Three starters."),
    ]
    pieces: list[str] = []
    make_loop(FakeLLM(steps)).run("sys", HISTORY, CTX, on_text=pieces.append)
    assert "".join(pieces) == "Three starters."


def test_a_failing_on_text_does_not_break_the_turn() -> None:
    def boom(_: str) -> None:
        raise RuntimeError("speaker unplugged")

    result = make_loop(FakeLLM([LLMResponse(text="Fine.")])).run("sys", HISTORY, CTX, on_text=boom)
    assert result.stop_reason == "answered" and result.text == "Fine."
