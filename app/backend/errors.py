"""Exceptions raised by BackendClient (PLAN.md section 4)."""


class BackendError(Exception):
    """Base class. The message is safe to show the model verbatim."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


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
