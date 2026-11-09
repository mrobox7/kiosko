"""What the page's trace panel and the voice endpoint show for a turn, and the counter that records
each model call into it. The events are plain records, one per thing that happened;
`api.schemas.trace_of` turns each into a dict tagged with its class name."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.llm.contract import LLMClient, LLMResponse
from app.llm.messages import Message, ToolSpec


@dataclass(frozen=True)
class GuardDecided:
    """The input guard's verdict on the customer message."""

    action: str
    reason: str


@dataclass(frozen=True)
class LLMCalled:
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class ItemsRecorded:
    """What `supervisor` made of the message: the reply language and the kind of each item."""

    language: str
    kinds: list[str]


@dataclass(frozen=True)
class ActionRun:
    """One item after a node dealt with it."""

    name: str
    status: str
    summary: str
    latency_ms: int = 0


@dataclass(frozen=True)
class TurnEnded:
    stop_reason: str
    detail: str = ""


TraceEvent = GuardDecided | LLMCalled | ItemsRecorded | ActionRun | TurnEnded


@dataclass
class Tally:
    events: list[TraceEvent] = field(default_factory=list)
    tokens: int = 0

    def _note(self, response: LLMResponse, started: float) -> LLMResponse:
        use = response.usage
        self.tokens += use.input_tokens + use.output_tokens
        ms = int((time.monotonic() - started) * 1000)
        self.events.append(LLMCalled(use.input_tokens, use.output_tokens, use.cached_tokens, ms))
        return response

    def complete(
        self,
        llm: LLMClient,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
        *,
        require_tool: bool = False,
    ) -> LLMResponse:
        started = time.monotonic()
        return self._note(llm.complete(system, messages, tools, require_tool=require_tool), started)

    def stream(
        self,
        llm: LLMClient,
        system: str,
        messages: Sequence[Message],
        on_text: Callable[[str], None],
    ) -> LLMResponse:
        started = time.monotonic()
        return self._note(llm.complete_stream(system, messages, on_text), started)

    def changes(self) -> dict[str, object]:
        """What a node returns for these calls."""
        return {"events": self.events, "tokens_used": self.tokens}
