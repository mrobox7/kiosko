import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnStarted:
    messages: int


@dataclass(frozen=True)
class LLMCalled:
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class ToolRequested:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolReturned:
    name: str
    ok: bool
    summary: str
    latency_ms: int


@dataclass(frozen=True)
class TurnEnded:
    stop_reason: str


TraceEvent = TurnStarted | LLMCalled | ToolRequested | ToolReturned | TurnEnded
Listener = Callable[[TraceEvent], None]


def emit(listener: Listener | None, event: TraceEvent) -> None:
    """Deliver an event; a failing listener never breaks the loop."""
    if listener is None:
        return
    try:
        listener(event)
    except Exception:  # boundary: observers must not affect the turn
        logger.exception("Trace listener failed")
