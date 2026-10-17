"""The agent loop: call the model, run its tools, repeat until it answers in text."""

import logging
import time
from collections.abc import Sequence

from app.agent.events import (
    Listener,
    LLMCalled,
    ToolRequested,
    ToolReturned,
    TurnEnded,
    TurnStarted,
    emit,
)
from app.domain.messages import Message, ToolCall, ToolOutcome
from app.domain.results import TOOL_CALL_BUDGET, LoopResult, StopReason, ToolResult
from app.domain.state import LedgerEntry
from app.llm.base import LLMClient, LLMError
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)
_CUT_NOTE = "...[result cut off]"


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class AgentLoop:
    """Stateless: history comes in, new messages go out."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        *,
        max_iterations: int,
        max_tool_calls: int,
        tool_result_max_chars: int,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls
        self._max_chars = tool_result_max_chars

    def run(
        self,
        system: str,
        history: Sequence[Message],
        ctx: ToolContext,
        listener: Listener | None = None,
    ) -> LoopResult:
        """Run until the model answers in text or a cap is hit."""
        messages = list(history)
        new: list[Message] = []
        writes: list[LedgerEntry] = []
        changes: list[str] = []
        tool_calls_used = 0
        specs = self._registry.specs()
        emit(listener, TurnStarted(messages=len(messages)))

        def finish(text: str, reason: StopReason, detail: str = "") -> LoopResult:
            emit(listener, TurnEnded(stop_reason=reason, detail=detail))
            return LoopResult(
                text=text, new_messages=new, stop_reason=reason, writes=writes, changes=changes
            )

        for _ in range(self._max_iterations):
            started = time.perf_counter()
            try:
                response = self._llm.complete(system, messages, specs)
            except LLMError as exc:
                logger.warning("LLM call failed (retryable=%s): %s", exc.retryable, exc)
                return finish("", "llm_error", detail=f"retryable={exc.retryable}: {exc}")
            usage = response.usage
            emit(
                listener,
                LLMCalled(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cached_tokens=usage.cached_tokens,
                    latency_ms=_ms(started),
                ),
            )
            if response.truncated:
                return finish(response.text or "", "truncated")

            assistant = Message(
                role="assistant", text=response.text, tool_calls=response.tool_calls
            )
            messages.append(assistant)
            new.append(assistant)
            if not response.tool_calls:
                return finish(response.text or "", "answered")

            outcomes: list[ToolOutcome] = []
            for call in response.tool_calls:
                tool_calls_used += 1
                over_budget = tool_calls_used > self._max_tool_calls
                outcome, result = self._run_call(call, ctx, listener, over_budget=over_budget)
                outcomes.append(outcome)
                writes.extend(result.writes)
                if result.writes:
                    changes.append(outcome.compact)
            results = Message(role="user", tool_outcomes=outcomes)
            messages.append(results)
            new.append(results)
        return finish("", "max_iterations")

    def _run_call(
        self, call: ToolCall, ctx: ToolContext, listener: Listener | None, *, over_budget: bool
    ) -> tuple[ToolOutcome, ToolResult]:
        """Exactly one outcome per call, always."""
        emit(listener, ToolRequested(name=call.name, arguments=call.arguments))
        started = time.perf_counter()
        if over_budget:
            result = ToolResult.failure(
                TOOL_CALL_BUDGET, "Too many tool calls this turn.", "Answer the customer now."
            )
        else:
            result = self._registry.dispatch(call.name, call.arguments, ctx, call.parse_error)
        content = result.model_dump_json(exclude_none=True, exclude={"writes"})
        if len(content) > self._max_chars:
            content = content[: self._max_chars] + _CUT_NOTE
        emit(
            listener,
            ToolReturned(
                name=call.name, ok=result.ok, summary=content[:160], latency_ms=_ms(started)
            ),
        )
        outcome = ToolOutcome(
            call_id=call.id,
            content=content,
            is_error=not result.ok,
            compact=self._registry.compact(call.name, call.arguments, result),
        )
        return outcome, result
