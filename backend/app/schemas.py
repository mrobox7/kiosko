"""What the API sends. Prices go out as plain JSON numbers (the server does all the arithmetic)."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, PlainSerializer, field_validator

Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class Category(BaseModel):
    id: int
    slug: str
    name: str


class Option(BaseModel, from_attributes=True):
    id: int
    name: str
    price_delta: Money
    is_default: bool
    linked_product_id: int | None  # set when the answer is itself a product


class OptionGroup(BaseModel):
    """A question for the customer. The limits are the ones that apply to this product."""

    id: int
    name: str
    min_select: int  # 1 or more: must be answered
    max_select: int
    options: list[Option]


class MealOffer(BaseModel):
    """'Make it a meal' for one product. A Large meal has no side choice."""

    size: str
    price_delta: Money
    side: OptionGroup | None
    drink: OptionGroup


class ProductSummary(BaseModel):
    id: int
    sku: str
    name: str
    description: str | None
    kind: str  # item | combo
    veg: str  # veg | non_veg
    category: str  # category slug
    base_price: Money
    image_url: str | None
    tags: list[str]


class ProductDetail(ProductSummary):
    nutrition: dict[str, Any]
    allergens: dict[str, Any]
    option_groups: list[OptionGroup]
    meal_offers: list[MealOffer]


class Catalog(BaseModel):
    """The whole menu. `version` changes whenever anything in it changes."""

    version: str
    categories: list[Category]
    products: list[ProductDetail]


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
    outlet_id: int
    lines: list[CartLine] = Field(min_length=1)


class PricedOption(BaseModel):
    option_id: int
    group: str
    name: str
    qty: int
    price_delta: Money
    total: Money  # price_delta x qty


class PricedLine(BaseModel):
    """`unit_price` is one item as configured; `line_total` is that times the quantity."""

    index: int  # position of the line in the request
    product_id: int
    name: str
    quantity: int
    meal_size: str | None
    base_price: Money
    meal_price: Money
    options_price: Money
    unit_price: Money
    line_total: Money
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
    subtotal: Money
    gst: Money
    total: Money
    missing: list[Issue]  # required questions not answered yet
    problems: list[Issue]  # things that are wrong and must change


_MOBILE = re.compile(r"(?:\+?91|0)?([6-9]\d{9})")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class OrderCreate(BaseModel):
    outlet_id: int
    phone: str  # an Indian mobile number; stored as +91 and ten digits
    email: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        match = _MOBILE.fullmatch(re.sub(r"[\s-]", "", value))
        if not match:
            raise ValueError("Enter a 10 digit Indian mobile number")
        return "+91" + match.group(1)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _EMAIL.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value.lower()


class OrderLineOut(BaseModel):
    id: int
    product_id: int
    name: str
    quantity: int
    meal_size: str | None
    note: str | None
    unit_price: Money
    line_total: Money
    options: list[PricedOption]


class OrderOut(BaseModel):
    """`subtotal`, `gst` and `total` of a draft change as lines change; once confirmed they are
    fixed."""

    id: int
    outlet_id: int
    phone: str
    email: str | None
    status: str  # draft | confirmed
    created_at: datetime
    confirmed_at: datetime | None
    lines: list[OrderLineOut]
    subtotal: Money
    gst: Money
    total: Money
