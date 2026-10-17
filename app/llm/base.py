"""The LLM contract: response types, client protocol, error."""

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from app.domain.messages import Message, ToolCall, ToolSpec

__all__ = ["LLMClient", "LLMError", "LLMResponse", "ToolSpec", "Usage"]


class Usage(BaseModel):
    """Token counts for one call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


class LLMResponse(BaseModel):
    """One model reply. `truncated` means the output hit the token limit."""

    text: str | None = None
    tool_calls: list[ToolCall] = []
    truncated: bool = False
    usage: Usage = Usage()


class LLMError(Exception):
    """Timeout, rate limit or provider error, after the adapter retried."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMClient(Protocol):
    """Anything that can answer one model call. Raises only LLMError."""

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        """Send the window to the model and return its reply."""
        ...
