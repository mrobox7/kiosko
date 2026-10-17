from app.llm.base import LLMResponse, Usage
from app.llm.fake import FakeLLM
from tests.support.builders import make_session


def test_guard_refuses_without_calling_the_llm() -> None:
    session, llm, _ = make_session([], max_chars=10)
    assert session.send("   ").stop_reason == "refused"
    long_reply = session.send("x" * 11)
    assert "too long" in long_reply.text and llm.calls == []


def test_rate_limit() -> None:
    session, _, _ = make_session([LLMResponse(text="a"), LLMResponse(text="b")], turns_per_min=2)
    assert session.send("1").stop_reason == "answered"
    assert session.send("2").stop_reason == "answered"
    assert session.send("3").stop_reason == "refused"


def test_token_budget_counts_usage_and_blocks() -> None:
    usage = Usage(input_tokens=60, output_tokens=40)
    session, _, _ = make_session([LLMResponse(text="a", usage=usage)], token_budget=100)
    assert session.send("1").stop_reason == "answered" and session.tokens_used == 100
    assert "limit" in session.send("2").text


def test_history_is_append_only_across_turns() -> None:
    session, llm, _ = make_session([LLMResponse(text="a"), LLMResponse(text="b")])
    session.send("one")
    session.send("two")
    assert isinstance(llm, FakeLLM)
    first, second = llm.calls[0].messages, llm.calls[1].messages
    assert second[: len(first)] == first
    assert llm.calls[0].system.split("\n\n")[0] == llm.calls[1].system.split("\n\n")[0]
