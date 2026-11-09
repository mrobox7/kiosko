"""The message types the model client and the nodes share."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A tool request from the model. Arguments are raw and unvalidated."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    parse_error: str | None = None  # set when the model's arguments were not a JSON object


class ToolOutcome(BaseModel):
    """The answer to exactly one ToolCall."""

    call_id: str
    content: str


class ToolSpec(BaseModel):
    """A tool described to the model: its name, what it is for and its JSON schema."""

    name: str
    description: str
    parameters: dict[str, Any]


class Message(BaseModel):
    """One conversation message. `system` is the per-turn context put in front of the customer's
    message; it is never stored in history. An assistant message may carry tool_calls; the user
    message that follows carries the matching tool_outcomes."""

    role: Literal["system", "user", "assistant"]
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_outcomes: list[ToolOutcome] = Field(default_factory=list)
