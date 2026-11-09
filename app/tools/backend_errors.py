"""What a tool does when the ordering server does not simply say yes.

`settle` repeats a request whose connection dropped, but only after checking the server did not
already do it. `translate` and `refusal_for` say a refusal the way the model can act on: the
server's refusal carries a `code` and, for a cart, a `missing` list (questions not answered) and a
`problems` list (something wrong); each becomes one tool failure with a plain message and a hint.
`reread` fetches the order again when it changed behind the chat's back."""

import logging
from collections.abc import Callable
from typing import Any

from app.backend.errors import BackendError, BackendUnavailable
from app.tools.contract import ToolContext, ToolResult, Update

logger = logging.getLogger(__name__)


def settle[T](first: Callable[[], T], *, landed: Callable[[], T | None]) -> T:
    """Run `first`. If it fails in a way that may still have gone through, ask `landed` whether its
    effect is there (it returns the result if so, else None) and only then run `first` once more.
    For a request that is safe to repeat, `landed` can return None. A second failure is raised."""
    try:
        return first()
    except BackendUnavailable as exc:
        if not exc.may_have_been_processed:
            raise
        return landed() or first()


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
            "not_found", exc.message, "That id does not exist. Ask the customer to choose again."
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
            "The order is still open at the new prices (see the order above). Tell the customer "
            "the new total and place it again only after they agree.",
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


def refusal_for(ctx: ToolContext, exc: BackendError) -> ToolResult | None:
    """The tool failure for a server refusal, or None when it is not one that is known. An order
    that was finished behind the chat's back is re-read, and the failure carries it, so the chat
    shows it as it is."""
    result = translate(exc)
    if result is not None and exc.code == "order_closed":
        result.update = reread(ctx)
    return result


def reread(ctx: ToolContext) -> Update | None:
    """The chat's order as the server has it now, e.g. after its prices changed, as an update to
    apply. None when there is no order or it cannot be read: the chat keeps the copy it has."""
    if ctx.order is None:
        return None
    try:
        return Update(order=ctx.backend.get_order(ctx.order.id))
    except BackendError:
        logger.warning("Could not re-read order %s", ctx.order.id)
        return None
