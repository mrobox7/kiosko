"""Scripted LLM double for offline tests."""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.llm.contract import LLMResponse
from app.llm.messages import Message, ToolSpec


@dataclass
class LLMCall:
    """What the model was asked."""

    system: str
    messages: list[Message]
    tools: list[ToolSpec] = field(default_factory=list)
    require_tool: bool = False


class FakeLLM:
    """Replays scripted responses or exceptions and records every call."""

    def __init__(self, steps: Sequence[LLMResponse | Exception]) -> None:
        self._steps = list(steps)
        self.calls: list[LLMCall] = []

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
        *,
        require_tool: bool = False,
    ) -> LLMResponse:
        """Return the next scripted step; fail if called more often than scripted."""
        self.calls.append(LLMCall(system, list(messages), list(tools), require_tool))
        if not self._steps:
            raise AssertionError("FakeLLM called more times than scripted")
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def complete_stream(
        self,
        system: str,
        messages: Sequence[Message],
        on_text: Callable[[str], None],
    ) -> LLMResponse:
        """Like `complete`, handing the reply text to `on_text` one word at a time."""
        response = self.complete(system, messages)
        for word in re.findall(r"\S+\s*", response.text or ""):
            on_text(word)
        return response
