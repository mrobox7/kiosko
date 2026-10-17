"""Scripted LLM double for offline tests."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.messages import Message, ToolSpec
from app.llm.base import LLMResponse


@dataclass
class LLMCall:
    """What the model was asked."""

    system: str
    messages: list[Message]
    tools: list[ToolSpec]


class FakeLLM:
    """Replays scripted responses or exceptions and records every call."""

    def __init__(self, steps: Sequence[LLMResponse | Exception]) -> None:
        self._steps = list(steps)
        self.calls: list[LLMCall] = []

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        """Return the next scripted step; fail if called more often than scripted."""
        self.calls.append(LLMCall(system, list(messages), list(tools)))
        if not self._steps:
            raise AssertionError("FakeLLM called more times than scripted")
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step
