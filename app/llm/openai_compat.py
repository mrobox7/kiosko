"""Adapter for any OpenAI-compatible chat API. The only file importing the SDK."""

import json
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, cast

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from app.domain.messages import Message, ToolCall, ToolSpec
from app.llm.base import LLMError, LLMResponse, Usage

logger = logging.getLogger(__name__)


def _to_provider_messages(system: str, messages: Sequence[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": m.text or ""}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in m.tool_calls
                ]
            out.append(entry)
        elif m.role == "system":
            out.append({"role": "system", "content": m.text or ""})
        else:
            out.extend(
                {"role": "tool", "tool_call_id": o.call_id, "content": o.content}
                for o in m.tool_outcomes
            )
            if m.text is not None:
                out.append({"role": "user", "content": m.text})
    return out


def _parse_tool_call(call_id: str, name: str, raw_arguments: str) -> ToolCall:
    if not raw_arguments.strip():
        return ToolCall(id=call_id, name=name)
    try:
        arguments = json.loads(raw_arguments)
    except ValueError as exc:
        return ToolCall(id=call_id, name=name, parse_error=f"Invalid JSON: {exc}")
    if not isinstance(arguments, dict):
        return ToolCall(id=call_id, name=name, parse_error="Arguments must be a JSON object")
    return ToolCall(id=call_id, name=name, arguments=arguments)


def _is_retryable(exc: openai.OpenAIError) -> bool:
    if isinstance(exc, openai.APIConnectionError | openai.RateLimitError):
        return True  # APITimeoutError is a subclass of APIConnectionError
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


def _usage(raw: Any) -> Usage:
    if raw is None:
        return Usage()
    details = getattr(raw, "prompt_tokens_details", None)
    return Usage(
        input_tokens=raw.prompt_tokens,
        output_tokens=raw.completion_tokens,
        cached_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
    )


class OpenAICompatLLM:
    """LLMClient over the OpenAI SDK, with bounded retry on transient failures."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        *,
        max_output_tokens: int = 1024,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._retries = retries
        self._sleep = sleep

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        """Call the provider and convert its reply."""
        reply = self._create(self._request(system, messages, tools))
        if not reply.choices:
            raise LLMError("Provider returned no choices")
        choice = reply.choices[0]
        calls = [
            _parse_tool_call(c.id, c.function.name, c.function.arguments)
            for c in choice.message.tool_calls or []
            if c.type == "function"
        ]
        return LLMResponse(
            text=choice.message.content,
            tool_calls=calls,
            truncated=choice.finish_reason == "length",
            usage=_usage(reply.usage),
        )

    def complete_stream(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        on_text: Callable[[str], None],
    ) -> LLMResponse:
        """Stream the reply: text goes to `on_text` as it arrives, tool calls are assembled from
        their pieces. Retries only cover opening the stream; once text may have been passed on,
        a failure is raised."""
        kwargs = {
            **self._request(system, messages, tools),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        stream = self._create(kwargs)
        text: list[str] = []
        pending: dict[int, dict[str, str]] = {}
        finish: str | None = None
        usage = Usage()
        try:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = _usage(chunk.usage)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta.content:
                    text.append(choice.delta.content)
                    on_text(choice.delta.content)
                for piece in choice.delta.tool_calls or []:
                    call = pending.setdefault(piece.index, {"id": "", "name": "", "args": ""})
                    call["id"] = piece.id or call["id"]
                    if piece.function:
                        call["name"] = piece.function.name or call["name"]
                        call["args"] += piece.function.arguments or ""
                finish = choice.finish_reason or finish
        except openai.OpenAIError as exc:
            raise LLMError(str(exc), retryable=False) from exc
        calls = [
            _parse_tool_call(c["id"], c["name"], c["args"])
            for _, c in sorted(pending.items())
            if c["name"]
        ]
        return LLMResponse(
            text="".join(text) or None,
            tool_calls=calls,
            truncated=finish == "length",
            usage=usage,
        )

    def _request(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": cast(
                list[ChatCompletionMessageParam], _to_provider_messages(system, messages)
            ),
            "max_completion_tokens": self._max_output_tokens,
        }
        if tools:
            kwargs["tools"] = cast(
                list[ChatCompletionToolParam],
                [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        },
                    }
                    for t in tools
                ],
            )
        return kwargs

    def _create(self, kwargs: dict[str, Any]) -> Any:
        """The provider call, with bounded retry on transient failures."""
        for attempt in range(self._retries + 1):
            try:
                return self._client.chat.completions.create(**kwargs)
            except openai.OpenAIError as exc:
                retryable = _is_retryable(exc)
                if not retryable or attempt == self._retries:
                    raise LLMError(str(exc), retryable=retryable) from exc
                logger.warning("LLM call failed (%s), retrying", type(exc).__name__)
                self._sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover
