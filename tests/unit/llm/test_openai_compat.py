from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from app.llm.contract import LLMError
from app.llm.messages import Message, ToolCall, ToolOutcome, ToolSpec
from app.llm.openai_compat import OpenAICompatLLM


def reply(content=None, finish="stop"):
    usage = NS(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=NS(cached_tokens=3))
    return NS(choices=[NS(message=NS(content=content), finish_reason=finish)], usage=usage)


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


def test_text_reply_and_usage() -> None:
    c, _ = llm([reply("hi")])
    r = c.complete("sys", [Message(role="user", text="yo")])
    assert r.text == "hi" and r.usage.cached_tokens == 3 and not r.truncated


def test_message_conversion() -> None:
    c, sdk = llm([reply("ok")])
    history = [
        Message(role="user", text="menu?"),
        Message(role="assistant", text="We have burgers."),
        Message(role="system", text="Context"),
        Message(role="user", text="ok"),
    ]
    c.complete("sys", history)
    msgs = sdk.kwargs[0]["messages"]
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("system", "sys"),
        ("user", "menu?"),
        ("assistant", "We have burgers."),
        ("system", "Context"),
        ("user", "ok"),
    ]


def test_truncated_flag() -> None:
    c, _ = llm([reply("cut", finish="length")])
    assert c.complete("s", []).truncated


def test_retries_transient_then_succeeds() -> None:
    sleeps: list[float] = []
    c, sdk = llm([openai.APITimeoutError(REQ), openai.APITimeoutError(REQ), reply("ok")], sleeps)
    assert c.complete("s", []).text == "ok"
    assert len(sdk.kwargs) == 3 and len(sleeps) == 2


def test_gives_up_after_retries() -> None:
    c, sdk = llm([openai.APITimeoutError(REQ)] * 3)
    with pytest.raises(LLMError) as info:
        c.complete("s", [])
    assert info.value.retryable and len(sdk.kwargs) == 3


def test_malformed_tool_call_is_retried() -> None:
    body = {"message": "Failed to call a function", "code": "tool_use_failed"}
    err = openai.BadRequestError("bad", response=httpx.Response(400, request=REQ), body=body)
    c, sdk = llm([err, reply("ok")])
    assert c.complete("s", []).text == "ok" and len(sdk.kwargs) == 2


def test_non_retryable_fails_immediately() -> None:
    err = openai.BadRequestError("bad", response=httpx.Response(400, request=REQ), body=None)
    c, sdk = llm([err])
    with pytest.raises(LLMError) as info:
        c.complete("s", [])
    assert not info.value.retryable and len(sdk.kwargs) == 1


def chunk(content=None, finish=None, usage=None):
    """One streamed piece of reply text."""
    return NS(choices=[NS(delta=NS(content=content), finish_reason=finish)], usage=usage)


def usage_only(prompt=10, completion=5, cached=3):
    usage = NS(
        prompt_tokens=prompt,
        completion_tokens=completion,
        prompt_tokens_details=NS(cached_tokens=cached),
    )
    return NS(choices=[], usage=usage)


def stream(c):
    pieces = []
    r = c.complete_stream("sys", [Message(role="user", text="yo")], pieces.append)
    return r, pieces


def test_stream_passes_text_on_as_it_arrives_and_returns_the_whole_reply() -> None:
    c, sdk = llm([iter([chunk("Hello "), chunk("there."), chunk(finish="stop"), usage_only()])])
    r, pieces = stream(c)
    assert pieces == ["Hello ", "there."] and r.text == "Hello there."
    assert r.usage.input_tokens == 10 and r.usage.cached_tokens == 3 and not r.truncated
    assert sdk.kwargs[0]["stream"] is True
    assert sdk.kwargs[0]["stream_options"] == {"include_usage": True}


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
        c.complete_stream("sys", [Message(role="user", text="yo")], pieces.append)
    assert pieces == ["Hel"] and info.value.retryable is False and len(sdk.kwargs) == 1


def tool_reply(*calls):
    """A provider reply that asks for tools: each call is (id, name, raw JSON arguments)."""
    made = [NS(id=i, type="function", function=NS(name=n, arguments=a)) for i, n, a in calls]
    usage = NS(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None)
    message = NS(content=None, tool_calls=made)
    return NS(choices=[NS(message=message, finish_reason="tool_calls")], usage=usage)


SPEC = ToolSpec(name="get_menu", description="Browse the menu.", parameters={"type": "object"})


def test_tools_are_described_to_the_provider_and_can_be_required() -> None:
    c, sdk = llm([reply("a"), reply("b"), reply("c")])
    c.complete("sys", [Message(role="user", text="x")])
    c.complete("sys", [Message(role="user", text="x")], [SPEC])
    c.complete("sys", [Message(role="user", text="x")], [SPEC], require_tool=True)
    plain, offered, required = sdk.kwargs
    assert "tools" not in plain and "tool_choice" not in plain
    assert offered["tools"] == [
        {
            "type": "function",
            "function": {"name": "get_menu", "description": "Browse the menu.",
                         "parameters": {"type": "object"}},
        }
    ] and "tool_choice" not in offered  # fmt: skip
    assert required["tool_choice"] == "required"


def test_tool_calls_are_parsed_and_bad_arguments_are_marked() -> None:
    c, _ = llm([tool_reply(("1", "get_menu", '{"veg": true}'), ("2", "get_item", "{oops"))])
    good, bad = c.complete("sys", [Message(role="user", text="x")], [SPEC]).tool_calls
    assert (good.id, good.name, good.arguments, good.parse_error) == (
        "1",
        "get_menu",
        {"veg": True},
        None,
    )
    assert bad.arguments == {} and bad.parse_error is not None


def test_tool_calls_and_their_results_go_back_in_the_provider_format() -> None:
    c, sdk = llm([reply("ok")])
    asked = ToolCall(id="1", name="get_menu", arguments={"veg": True})
    c.complete(
        "sys",
        [
            Message(role="user", text="veg?"),
            Message(role="assistant", tool_calls=[asked]),
            Message(role="user", tool_outcomes=[ToolOutcome(call_id="1", content='{"ok":true}')]),
        ],
    )
    msgs = sdk.kwargs[0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[2]["tool_calls"][0]["function"] == {
        "name": "get_menu",
        "arguments": '{"veg": true}',
    }
    assert msgs[3] == {"role": "tool", "tool_call_id": "1", "content": '{"ok":true}'}
