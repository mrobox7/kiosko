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
        for attempt in range(self._retries + 1):
            try:
                reply = self._client.chat.completions.create(**kwargs)
                break
            except openai.OpenAIError as exc:
                retryable = _is_retryable(exc)
                if not retryable or attempt == self._retries:
                    raise LLMError(str(exc), retryable=retryable) from exc
                logger.warning("LLM call failed (%s), retrying", type(exc).__name__)
                self._sleep(0.5 * 2**attempt)
        if not reply.choices:
            raise LLMError("Provider returned no choices")
        choice = reply.choices[0]
        calls = [
            _parse_tool_call(c.id, c.function.name, c.function.arguments)
            for c in choice.message.tool_calls or []
            if c.type == "function"
        ]
        usage = Usage()
        if reply.usage:
            details = reply.usage.prompt_tokens_details
            usage = Usage(
                input_tokens=reply.usage.prompt_tokens,
                output_tokens=reply.usage.completion_tokens,
                cached_tokens=(details.cached_tokens or 0) if details else 0,
            )
        return LLMResponse(
            text=choice.message.content,
            tool_calls=calls,
            truncated=choice.finish_reason == "length",
            usage=usage,
        )
