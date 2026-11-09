"""Exceptions raised by BackendClient."""

from typing import Any


class BackendError(Exception):
    """Base class. The message is safe to show the model verbatim.

    A refusal from the ordering server also carries its `code` (`not_found`, `order_closed`,
    `empty_order`, `invalid_line`, `cannot_confirm`) and, for a cart, the `missing` and `problems`
    lists as the server sent them, each entry with its own `code`."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        *,
        code: str | None = None,
        missing: list[dict[str, Any]] | None = None,
        problems: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.missing = missing or []
        self.problems = problems or []


class BackendNotFound(BackendError):
    """404."""


class BackendConflict(BackendError):
    """409, for example a slot already taken."""


class BackendRuleViolation(BackendError):
    """Any other 4xx rejection. Carries the backend message."""


class BackendUnavailable(BackendError):
    """Timeout, connection error or 5xx."""

    def __init__(
        self, message: str, status: int | None = None, may_have_been_processed: bool = False
    ) -> None:
        super().__init__(message, status)
        self.may_have_been_processed = may_have_been_processed
