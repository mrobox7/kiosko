"""Conversation vocabulary shared by every layer."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A tool request from the model. Arguments are raw and unvalidated."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    parse_error: str | None = None


class ToolOutcome(BaseModel):
    """The answer to exactly one ToolCall."""

    call_id: str
    content: str
    is_error: bool = False
    compact: str = ""  # one-line form for the turn summary; never sent to the model


class Message(BaseModel):
    """One conversation turn. Assistant turns carry tool_calls; the user-side turn
    that follows carries the matching tool_outcomes."""

    role: Literal["user", "assistant"]
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_outcomes: list[ToolOutcome] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """Tool description sent to the model."""

    name: str
    description: str
    parameters: dict[str, Any]
