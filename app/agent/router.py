"""Where the turn goes next, decided in code from the item statuses. No model is asked."""

from typing import Literal

from app.agent.items import Item

Step = Literal["searcher", "executor", "respond"]
LAST = ("place", "cancel")  # these wait until nothing else is unresolved


def unresolved(items: list[Item]) -> bool:
    return any(i.status in ("needs_search", "needs_user") for i in items)


def runnable(items: list[Item]) -> list[Item]:
    """The ready items that may run now: all of them, except that placing or cancelling the order
    waits while anything else the customer asked for is still unresolved."""
    waiting = unresolved(items)
    return [i for i in items if i.status == "ready" and not (waiting and i.kind in LAST)]


def next_step(items: list[Item]) -> Step:
    """Search what is unknown first. Then make the changes that are clear (the executor also
    reports a held place or cancel). Otherwise reply. Every item moves through its statuses once,
    so the turn cannot loop."""
    if any(i.status == "needs_search" for i in items):
        return "searcher"
    if any(i.status == "ready" for i in items):
        return "executor"
    return "respond"
