"""What the order and price endpoints accept and send."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.menu.schemas import DecimalNumber


class OptionPick(BaseModel):
    """A chosen option. `qty` above 1 means the same option more than once (two cheese)."""

    option_id: int
    qty: int = Field(default=1, ge=1)


class CartLine(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)
    meal_size: str | None = None  # a size from the product's meal offers
    options: list[OptionPick] = []
    note: str | None = Field(default=None, max_length=200)  # a special request; kept, never priced


class PriceRequest(BaseModel):
    outlet: str  # the outlet's code
    lines: list[CartLine] = Field(min_length=1)


class PricedOption(BaseModel):
    option_id: int
    group: str
    name: str
    qty: int
    price_delta: DecimalNumber
    total: DecimalNumber  # price_delta x qty


class PricedLine(BaseModel):
    """`unit_price` is one item as configured; `line_total` is that times the quantity."""

    index: int  # position of the line in the request
    product_id: int
    name: str
    quantity: int
    meal_size: str | None
    base_price: DecimalNumber
    meal_price: DecimalNumber
    options_price: DecimalNumber
    unit_price: DecimalNumber
    line_total: DecimalNumber
    options: list[PricedOption]


class Issue(BaseModel):
    """`code` is one of: required, too_many, unknown_option, not_on_menu, unavailable,
    no_such_meal, price_changed."""

    line: int
    code: str
    message: str
    group_id: int | None = None


class PricedCart(BaseModel):
    """`ready` is true when nothing is missing and nothing is wrong. Lines that can be priced
    are priced even when the cart is not ready."""

    ready: bool
    lines: list[PricedLine]
    subtotal: DecimalNumber
    gst: DecimalNumber
    total: DecimalNumber
    missing: list[Issue]  # required questions not answered yet
    problems: list[Issue]  # things that are wrong and must change


class OrderCreate(BaseModel):
    outlet: str  # the outlet's code
    customer_id: int | None = None  # orders may start anonymous and get a customer later


class AttachCustomer(BaseModel):
    customer_id: int


class LineQuantity(BaseModel):
    quantity: int = Field(ge=1)


class OrderLineOut(BaseModel):
    id: int
    product_id: int
    name: str
    quantity: int
    meal_size: str | None
    note: str | None
    unit_price: DecimalNumber
    line_total: DecimalNumber
    options: list[PricedOption]


class OrderOut(BaseModel):
    """`subtotal`, `gst` and `total` of a draft change as lines change; once confirmed they are
    fixed."""

    id: int
    outlet: str  # the outlet's code
    customer_id: int | None
    status: str  # draft | confirmed | cancelled
    order_number: int | None  # the number called out at the window; set when confirmed
    created_at: datetime
    confirmed_at: datetime | None
    lines: list[OrderLineOut]
    subtotal: DecimalNumber
    gst: DecimalNumber
    total: DecimalNumber
