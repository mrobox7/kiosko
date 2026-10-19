from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from app.domain.messages import Message, ToolCall, ToolOutcome, ToolSpec
from app.llm.base import LLMError
from app.llm.openai_compat import OpenAICompatLLM


def reply(content=None, calls=(), finish="stop"):
    tcs = [NS(id=i, type="function", function=NS(name=n, arguments=a)) for i, n, a in calls] or None
    usage = NS(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=NS(cached_tokens=3))
    return NS(
        choices=[NS(message=NS(content=content, tool_calls=tcs), finish_reason=finish)], usage=usage
    )


class StubSDK:
    def __init__(self, steps):
        self.steps, self.kwargs = list(steps), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.kwargs.append(kw)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def llm(steps, sleeps=None):
    sdk = StubSDK(steps)
    sleeps = [] if sleeps is None else sleeps
    return OpenAICompatLLM(sdk, "m", retries=2, sleep=sleeps.append), sdk


REQ = httpx.Request("POST", "http://x")
SPEC = ToolSpec(name="t", description="d", parameters={"type": "object"})


def test_text_reply_and_usage() -> None:
    c, _ = llm([reply("hi")])
    r = c.complete("sys", [Message(role="user", text="yo")], [])
    assert r.text == "hi" and r.usage.cached_tokens == 3 and not r.truncated


def test_message_and_tool_conversion() -> None:
    c, sdk = llm([reply("ok")])
    history = [
        Message(role="user", text="menu?"),
        Message(role="assistant", tool_calls=[ToolCall(id="1", name="t", arguments={"a": 1})]),
        Message(role="user", tool_outcomes=[ToolOutcome(call_id="1", content="{}")]),
    ]
    c.complete("sys", history, [SPEC])
    msgs = sdk.kwargs[0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert msgs[3]["tool_call_id"] == "1"
    assert sdk.kwargs[0]["tools"][0]["function"]["name"] == "t"


def test_tool_call_parsing_and_parse_error() -> None:
    c, _ = llm([reply(calls=[("1", "t", '{"a": 1}'), ("2", "t", "{oops"), ("3", "t", "")])])
    calls = c.complete("s", [], []).tool_calls
    assert calls[0].arguments == {"a": 1} and calls[0].parse_error is None
    assert calls[1].parse_error and calls[2].arguments == {}


def test_truncated_flag() -> None:
    c, _ = llm([reply("cut", finish="length")])
    assert c.complete("s", [], []).truncated


def test_retries_transient_then_succeeds() -> None:
    sleeps: list[float] = []
    c, sdk = llm([openai.APITimeoutError(REQ), openai.APITimeoutError(REQ), reply("ok")], sleeps)
    assert c.complete("s", [], []).text == "ok"
    assert len(sdk.kwargs) == 3 and len(sleeps) == 2


def test_gives_up_after_retries() -> None:
    c, sdk = llm([openai.APITimeoutError(REQ)] * 3)
    with pytest.raises(LLMError) as info:
        c.complete("s", [], [])
    assert info.value.retryable and len(sdk.kwargs) == 3


def test_non_retryable_fails_immediately() -> None:
    err = openai.BadRequestError("bad", response=httpx.Response(400, request=REQ), body=None)
    c, sdk = llm([err])
    with pytest.raises(LLMError) as info:
        c.complete("s", [], [])
    assert not info.value.retryable and len(sdk.kwargs) == 1


def chunk(content=None, calls=(), finish=None, usage=None):
    """One streamed piece. `calls` are (index, id, name, arguments) fragments."""
    pieces = [
        NS(index=i, id=cid, function=NS(name=name, arguments=args)) for i, cid, name, args in calls
    ]
    delta = NS(content=content, tool_calls=pieces or None)
    return NS(choices=[NS(delta=delta, finish_reason=finish)], usage=usage)


def usage_only(prompt=10, completion=5, cached=3):
    usage = NS(
        prompt_tokens=prompt,
        completion_tokens=completion,
        prompt_tokens_details=NS(cached_tokens=cached),
    )
    return NS(choices=[], usage=usage)


def stream(c):
    pieces = []
    r = c.complete_stream("sys", [Message(role="user", text="yo")], [SPEC], pieces.append)
    return r, pieces


def test_stream_passes_text_on_as_it_arrives_and_returns_the_whole_reply() -> None:
    c, sdk = llm([iter([chunk("Hello "), chunk("there."), chunk(finish="stop"), usage_only()])])
    r, pieces = stream(c)
    assert pieces == ["Hello ", "there."] and r.text == "Hello there."
    assert r.usage.input_tokens == 10 and r.usage.cached_tokens == 3 and not r.truncated
    assert sdk.kwargs[0]["stream"] is True
    assert sdk.kwargs[0]["stream_options"] == {"include_usage": True}


def test_stream_assembles_tool_calls_from_fragments() -> None:
    c, _ = llm(
        [
            iter(
                [
                    chunk(calls=[(0, "c1", "t", '{"a": ')]),
                    chunk(calls=[(0, None, None, "1}")]),
                    chunk(calls=[(1, "c2", "u", "")]),
                    chunk(finish="tool_calls"),
                ]
            )
        ]
    )
    r, pieces = stream(c)
    assert pieces == [] and r.text is None
    assert [(t.id, t.name, t.arguments) for t in r.tool_calls] == [
        ("c1", "t", {"a": 1}),
        ("c2", "u", {}),
    ]


def test_stream_keeps_bad_tool_arguments_as_a_parse_error() -> None:
    c, _ = llm([iter([chunk(calls=[(0, "c1", "t", "{oops")]), chunk(finish="tool_calls")])])
    r, _ = stream(c)
    assert r.tool_calls[0].parse_error is not None


def test_stream_text_before_a_tool_call_is_kept_with_it() -> None:
    c, _ = llm(
        [iter([chunk("One moment. "), chunk(calls=[(0, "c1", "t", "{}")]), chunk(finish="stop")])]
    )
    r, pieces = stream(c)
    assert pieces == ["One moment. "] and r.text == "One moment. " and r.tool_calls[0].name == "t"


def test_stream_truncated_flag() -> None:
    c, _ = llm([iter([chunk("cut", finish="length")])])
    r, _ = stream(c)
    assert r.truncated and r.usage.input_tokens == 0


def test_stream_retries_opening_the_stream_then_succeeds() -> None:
    sleeps: list[float] = []
    c, sdk = llm(
        [openai.APIConnectionError(request=REQ), iter([chunk("ok"), chunk(finish="stop")])], sleeps
    )
    r, pieces = stream(c)
    assert r.text == "ok" and pieces == ["ok"] and len(sdk.kwargs) == 2 and sleeps == [0.5]


def test_stream_failure_after_text_is_raised_not_retried() -> None:
    def broken():
        yield chunk("Hel")
        raise openai.APIConnectionError(request=REQ)

    c, sdk = llm([broken()])
    pieces: list[str] = []
    with pytest.raises(LLMError) as info:
        c.complete_stream("sys", [Message(role="user", text="yo")], [], pieces.append)
    assert pieces == ["Hel"] and info.value.retryable is False and len(sdk.kwargs) == 1
