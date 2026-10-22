"""Checks a cart against the menu and prices it. Nothing is stored.

line price = base price + meal price + chosen options' price changes
GST is worked out once on the whole order.

A required question left unanswered takes its default, if it has exactly one."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.menu.availability import Availability
from app.menu.models import MealOffer, OptionGroup, Product
from app.menu.service import DETAIL
from app.orders import schemas

GST_RATE = Decimal("0.05")
PAISA = Decimal("0.01")


def gst(subtotal: Decimal) -> Decimal:
    return (subtotal * GST_RATE).quantize(PAISA, rounding=ROUND_HALF_UP)


class _Group:
    """A question this product asks, with the limits that apply to it."""

    def __init__(self, group: OptionGroup, low: int | None, high: int | None) -> None:
        self.group = group
        self.low = group.min_select if low is None else low
        self.high = group.max_select if high is None else high


def _questions(product: Product, offer: MealOffer | None) -> dict[int, _Group]:
    asked = {
        link.group_id: _Group(link.group, link.min_select, link.max_select)
        for link in product.option_links
    }
    if offer:
        for meal_group in (offer.side_group, offer.drink_group):
            if meal_group and meal_group.id not in asked:
                asked[meal_group.id] = _Group(meal_group, None, None)
    return asked


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _use_default(asked: _Group, sale: Availability, chosen: list[schemas.PricedOption]) -> int:
    """A required question the customer did not answer is answered by its default, when it has
    exactly one that is on sale (ketchup on a burger). Returns how many picks that added, 0 if the
    question has no single default and so still has to be asked."""
    defaults = [o for o in asked.group.options if o.is_default and sale.has(o)]
    if len(defaults) != 1:
        return 0
    option = defaults[0]
    chosen.append(
        schemas.PricedOption(
            option_id=option.id,
            group=asked.group.name,
            name=option.name,
            qty=asked.low,
            price_delta=option.price_delta,
            total=option.price_delta * asked.low,
        )
    )
    return asked.low


def _price_line(
    index: int,
    line: schemas.CartLine,
    product: Product | None,
    sale: Availability,
) -> tuple[schemas.PricedLine | None, list[schemas.Issue], list[schemas.Issue]]:
    """Price one line. Returns the priced line (None if it cannot be priced) and its issues:
    what is missing, and what is wrong."""
    missing: list[schemas.Issue] = []
    problems: list[schemas.Issue] = []

    def problem(code: str, message: str, group_id: int | None = None) -> None:
        problems.append(schemas.Issue(line=index, code=code, message=message, group_id=group_id))

    if product is None or not product.is_active:
        problem("not_on_menu", f"Product {line.product_id} is not on the menu")
        return None, missing, problems
    if not sale.sells(product):
        problem("unavailable", f"{product.name} is not available at this outlet")
        return None, missing, problems
    base = product.base_price

    offer = None
    if line.meal_size:
        offer = next((m for m in product.meal_offers if m.size == line.meal_size), None)
        if offer is None:
            problem("no_such_meal", f"{product.name} has no {line.meal_size} meal")
        elif not sale.meal_ok(offer):
            problem("unavailable", f"{product.name} {offer.size} meal is not available here")
            offer = None
    meal_price = offer.price_delta if offer else Decimal(0)

    questions = _questions(product, offer)
    offered = {o.id: (o, g.group) for g in questions.values() for o in g.group.options}
    picked: defaultdict[int, int] = defaultdict(int)  # option id -> quantity
    for pick in line.options:
        picked[pick.option_id] += pick.qty

    chosen: list[schemas.PricedOption] = []
    in_group: defaultdict[int, int] = defaultdict(int)
    for option_id, qty in picked.items():
        if option_id not in offered:
            problem("unknown_option", f"Option {option_id} is not offered for {product.name}")
            continue
        option, group = offered[option_id]
        if not sale.has(option):
            problem("unavailable", f"{option.name} is not available at this outlet")
            continue
        in_group[group.id] += qty
        chosen.append(
            schemas.PricedOption(
                option_id=option.id,
                group=group.name,
                name=option.name,
                qty=qty,
                price_delta=option.price_delta,
                total=option.price_delta * qty,
            )
        )
    for group_id, asked in questions.items():
        count = in_group[group_id]
        if count == 0 and asked.low > 0:
            count += _use_default(asked, sale, chosen)
        if count < asked.low:
            need = _plural(asked.low - count, "choice")
            message = f"{product.name}: {asked.group.name} still needs {need}"
            missing.append(
                schemas.Issue(line=index, code="required", message=message, group_id=group_id)
            )
        elif count > asked.high:
            message = f"{product.name}: {asked.group.name} allows at most {asked.high}, got {count}"
            problem("too_many", message, group_id)

    options_price = sum((c.total for c in chosen), Decimal(0))
    unit = base + meal_price + options_price
    priced = schemas.PricedLine(
        index=index,
        product_id=product.id,
        name=product.name,
        quantity=line.quantity,
        meal_size=offer.size if offer else None,
        base_price=base,
        meal_price=meal_price,
        options_price=options_price,
        unit_price=unit,
        line_total=unit * line.quantity,
        options=chosen,
    )
    return priced, missing, problems


def price_cart(db: Session, outlet_id: int, lines: list[schemas.CartLine]) -> schemas.PricedCart:
    products = {
        p.id: p
        for p in db.scalars(
            select(Product)
            .where(Product.id.in_({line.product_id for line in lines}))
            .options(*DETAIL)
        )
    }
    sale = Availability.for_outlet(db, outlet_id)
    priced: list[schemas.PricedLine] = []
    missing: list[schemas.Issue] = []
    problems: list[schemas.Issue] = []
    for index, line in enumerate(lines):
        one, line_missing, line_problems = _price_line(
            index, line, products.get(line.product_id), sale
        )
        if one:
            priced.append(one)
        missing += line_missing
        problems += line_problems

    subtotal = sum((p.line_total for p in priced), Decimal(0))
    tax = gst(subtotal)
    return schemas.PricedCart(
        ready=not missing and not problems,
        lines=priced,
        subtotal=subtotal,
        gst=tax,
        total=subtotal + tax,
        missing=missing,
        problems=problems,
    )
