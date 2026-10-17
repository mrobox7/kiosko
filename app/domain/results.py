"""Results returned by tools and by the agent loop."""

from typing import Any, Literal

from pydantic import BaseModel

from app.domain.messages import Message

# Error codes a tool result can carry (PLAN.md section 8, dispatcher contract).
MALFORMED_ARGUMENTS_JSON = "malformed_arguments_json"
UNKNOWN_TOOL = "unknown_tool"
INVALID_ARGUMENTS = "invalid_arguments"
BACKEND_REJECTED = "backend_rejected"
BACKEND_UNAVAILABLE = "backend_unavailable"
INTERNAL_ERROR = "internal_error"
TOOL_CALL_BUDGET = "tool_call_budget"


class ToolError(BaseModel):
    """Error code plus a message and an optional hint the model can act on."""

    code: str
    message: str
    hint: str | None = None


class ToolResult(BaseModel):
    """What a tool hands back to the loop: data on success, an error otherwise."""

    ok: bool
    data: Any = None
    error: ToolError | None = None

    @classmethod
    def success(cls, data: Any) -> ToolResult:
        """A successful result."""
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: str, message: str, hint: str | None = None) -> ToolResult:
        """A failed result."""
        return cls(ok=False, error=ToolError(code=code, message=message, hint=hint))


StopReason = Literal["answered", "max_iterations", "llm_error", "truncated"]


class LoopResult(BaseModel):
    """Outcome of one agent-loop run."""

    text: str
    new_messages: list[Message]
    stop_reason: StopReason
