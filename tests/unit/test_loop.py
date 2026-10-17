from app.agent.events import ToolRequested, ToolReturned, TurnEnded
from app.agent.loop import AgentLoop
from app.domain.messages import Message, ToolCall
from app.llm.base import LLMError, LLMResponse
from app.llm.fake import FakeLLM
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx

CTX = make_ctx()
HISTORY = [Message(role="user", text="vegetarian starters?")]


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


def call(id="c1", name="list_menu", **args):
    return LLMResponse(tool_calls=[ToolCall(id=id, name=name, arguments=args)])


def test_text_only() -> None:
    loop, _ = make([LLMResponse(text="Hello")])
    r = loop.run("sys", HISTORY, CTX)
    assert r.stop_reason == "answered" and r.text == "Hello"
    assert [m.role for m in r.new_messages] == ["assistant"]


def test_tool_call_then_text_pairs_outcomes_and_traces() -> None:
    loop, llm = make([call(tags_any=["vegetarian"]), LLMResponse(text="Here you go")])
    events = []
    r = loop.run("sys", HISTORY, CTX, events.append)
    assert r.stop_reason == "answered"
    outcomes = r.new_messages[1].tool_outcomes
    assert [o.call_id for o in outcomes] == ["c1"] and not outcomes[0].is_error
    assert "Paneer Tikka" in outcomes[0].content
    # second model call saw the tool outcome
    assert llm.calls[1].messages[-1].tool_outcomes[0].call_id == "c1"
    kinds = [type(e) for e in events]
    assert ToolRequested in kinds and ToolReturned in kinds and kinds[-1] is TurnEnded


def test_iteration_cap() -> None:
    loop, _ = make([call(id=f"c{i}") for i in range(3)], max_iterations=3)
    r = loop.run("sys", HISTORY, CTX)
    assert r.stop_reason == "max_iterations" and len(r.new_messages) == 6


def test_tool_call_budget_still_pairs_every_call() -> None:
    many = LLMResponse(tool_calls=[ToolCall(id=f"c{i}", name="list_menu") for i in range(3)])
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


def test_large_result_is_capped() -> None:
    loop, _ = make([call(), LLMResponse(text="ok")], max_chars=100)
    r = loop.run("s", HISTORY, CTX)
    assert r.new_messages[1].tool_outcomes[0].content.endswith("[result cut off]")


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
