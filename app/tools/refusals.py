"""What the ordering server refused, said the way the model can act on.

The server's refusal carries a `code` and, for a cart, a `missing` list (questions not answered)
and a `problems` list (something wrong); each entry has its own code. This turns them into one tool
failure with a plain message and a hint for the next step. A refusal it does not know becomes
`backend_rejected` with the server's message, in the registry."""

from typing import Any

from app.backend.errors import BackendError
from app.domain.results import ToolResult


def _messages(issues: list[dict[str, Any]]) -> str:
    return "; ".join(i["message"] for i in issues if i.get("message"))


def translate(exc: BackendError) -> ToolResult | None:
    """The tool failure for a refusal, or None when it is not one this knows."""
    if exc.code == "invalid_line":
        return _line(exc)
    if exc.code == "cannot_confirm":
        return _confirm(exc)
    if exc.code == "empty_order":
        return ToolResult.failure("empty_order", "The order is empty.", "Add a dish first.")
    if exc.code == "order_closed":
        return ToolResult.failure(
            "order_closed",
            exc.message,
            "This order can no longer change. Tell the customer where it stands.",
        )
    if exc.code == "not_found":
        return ToolResult.failure(
            "not_found", exc.message, "That id does not exist. Check it with get_menu or get_order."
        )
    return None


def _line(exc: BackendError) -> ToolResult:
    """A dish that could not be added."""
    codes = {p.get("code") for p in exc.problems}
    if "unavailable" in codes:
        return ToolResult.failure(
            "unavailable",
            _messages(exc.problems),
            "Tell the customer it is not available here and offer something else.",
        )
    if exc.problems:
        return ToolResult.failure(
            "invalid_choice",
            _messages(exc.problems),
            "Nothing was added. Fix the choice, or ask the customer which they want.",
        )
    return ToolResult.failure(
        "incomplete",
        _messages(exc.missing),
        "Nothing was added. Ask the customer these questions, then call again with the answers.",
    )


def _confirm(exc: BackendError) -> ToolResult:
    """An order that could not be placed."""
    codes = {p.get("code") for p in exc.problems}
    if "price_changed" in codes:
        return ToolResult.failure(
            "price_changed",
            _messages(exc.problems),
            "The order is still open at the new prices (see get_order). Tell the customer the "
            "new total and place it again only after they agree.",
        )
    if "unavailable" in codes:
        return ToolResult.failure(
            "unavailable",
            _messages(exc.problems),
            "The order is still open. Tell the customer, remove that dish and offer another.",
        )
    return ToolResult.failure(
        "cannot_place", _messages(exc.problems) or exc.message, "The order is still open."
    )
