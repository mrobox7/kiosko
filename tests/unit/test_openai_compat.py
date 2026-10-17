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
