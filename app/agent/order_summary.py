"""The order summary a reply ends with, written by code from the order the server returned, so the
quantities, prices and total in a reply are never typed by the model. Spoken replies get the same
facts in words."""

from app.agent.items import Item
from app.backend.models import Order
from app.menu.names import dish_name

_UNITS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()
CHANGES = ("add", "remove", "change_qty")


def words(n: int) -> str:
    """A whole number in words, as it is said aloud (up to 99,999)."""
    if n < 20:
        return _UNITS[n]
    if n < 100:
        return _TENS[n // 10] + (f" {_UNITS[n % 10]}" if n % 10 else "")
    if n < 1000:
        return f"{_UNITS[n // 100]} hundred" + (f" {words(n % 100)}" if n % 100 else "")
    if n < 100_000:
        return f"{words(n // 1000)} thousand" + (f" {words(n % 1000)}" if n % 1000 else "")
    return str(n)


def spoken_amount(amount: float) -> str:
    rupees, paise = divmod(round(amount * 100), 100)
    text = f"{words(rupees)} rupees"
    return text + (f" and {words(paise)} paise" if paise else "")


def _lines(order: Order) -> list[tuple[int, str]]:
    return [(ln.quantity, dish_name(ln.name)) for ln in order.lines]


def _screen(order: Order, placed: bool) -> str:
    head = f"Order placed. Your number is {order.order_number}." if placed else "Your order:"
    lines = [f"{q} × {name}" for q, name in _lines(order)]
    return "\n".join([head, *lines, f"Total ₹{order.total:.2f}"])


def _spoken(order: Order, placed: bool) -> str:
    said = [f"{words(q)} {name}" for q, name in _lines(order)]
    have = f"{', '.join(said[:-1])} and {said[-1]}" if len(said) > 1 else "".join(said)
    head = (
        f"Your order is placed. Your number is {words(order.order_number or 0)}. " if placed else ""
    )
    return f"{head}You have {have}. The total is {spoken_amount(order.total)}."


def order_summary(order: Order | None, items: list[Item], spoken: bool) -> str:
    """The summary to end the reply with: after the order was placed or changed this turn, or when
    the customer asked to hear it. Empty otherwise, so a plain answer is not followed by a list."""
    if order is None:
        return ""
    done = {i.kind for i in items if i.status == "done"}
    placed = "place" in done and order.status == "confirmed"
    if not placed and not done.intersection((*CHANGES, "show_order")):
        return ""
    if not order.lines:
        return "Your order is empty."
    return _spoken(order, placed) if spoken else _screen(order, placed)
