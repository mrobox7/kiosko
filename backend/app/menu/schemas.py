"""What the menu endpoints send."""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer

# Exact Decimals inside the server; sent out as plain JSON numbers.
DecimalNumber = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class Category(BaseModel):
    id: int
    slug: str
    name: str


class Option(BaseModel, from_attributes=True):
    id: int
    name: str
    price_delta: DecimalNumber
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
    price_delta: DecimalNumber
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
    base_price: DecimalNumber
    image_url: str | None
    tags: list[str]


class ProductDetail(ProductSummary):
    nutrition: dict[str, Any]  # calories_kcal, protein_g, fat_g, carbs_g, sugar_g, sodium_mg
    allergens: list[str]  # what the item contains; an empty list means none
    option_groups: list[OptionGroup]
    meal_offers: list[MealOffer]


class Catalog(BaseModel):
    """The whole menu. `version` changes whenever anything in it changes."""

    version: str
    categories: list[Category]
    products: list[ProductDetail]


class CatalogVersion(BaseModel):
    version: str


class OutletInfo(BaseModel):
    """Who an outlet is: the code a drive-thru is set up with, its name and its address."""

    code: str
    name: str
    address: str


class Unavailable(BaseModel):
    """What one outlet is not selling right now."""

    products: list[int]
    options: list[int]
