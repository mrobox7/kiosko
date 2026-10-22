from typing import Any

from pydantic import BaseModel, Field


class Customer(BaseModel):
    """CustomerOut."""

    id: int
    name: str | None = None  # the ordering server does not ask for one
    phone: str | None
    email: str | None
    preferences: dict[str, Any] = Field(default_factory=dict)


class Favourite(BaseModel):
    """A dish this customer has ordered before (the server's Favourite)."""

    product_id: int
    name: str
    times_ordered: int
    total_quantity: int


class DriveThruLine(BaseModel):
    """One line of a drive-thru order: a dish with its choices (the server's order line)."""

    id: int
    product_id: int | None = None  # the dish; the kiosk screen shows its picture
    name: str
    quantity: int
    meal_size: str | None = None
    note: str | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    line_total: float  # for the whole line, before tax


class DriveThruOrder(BaseModel):
    """A drive-thru order, draft or placed."""

    id: int
    status: str  # draft | confirmed | cancelled
    customer_id: int | None = None
    order_number: int | None = None
    lines: list[DriveThruLine] = Field(default_factory=list)
    subtotal: float
    gst: float
    total: float


class MenuOption(BaseModel):
    """One answer to a question about a dish (a sauce, a meal side, a drink)."""

    id: int
    name: str
    price_delta: float = 0
    is_default: bool = False  # taken when a required question is left unanswered


class MenuOptionGroup(BaseModel):
    """A question about a dish. `min_select` of 1 or more means it must be answered."""

    id: int
    name: str
    min_select: int
    max_select: int
    options: list[MenuOption]


class MenuMealOffer(BaseModel):
    """'Make it a meal': a size, its extra price, and the side and drink questions it adds."""

    size: str  # Medium | Large
    price_delta: float
    side: MenuOptionGroup | None = None  # a Large meal has no side question
    drink: MenuOptionGroup


class MenuDish(BaseModel):
    """One dish with everything the customer can choose, as the server's catalog lists it."""

    id: int
    name: str
    description: str | None = None
    kind: str  # item | combo
    veg: str  # veg | non_veg
    category: str  # category slug
    base_price: float
    tags: list[str] = Field(default_factory=list)  # e.g. "bestseller"
    nutrition: dict[str, Any] = Field(default_factory=dict)  # calories_kcal, protein_g, ...
    allergens: list[str] = Field(default_factory=list)  # empty means none listed
    option_groups: list[MenuOptionGroup] = Field(default_factory=list)
    meal_offers: list[MenuMealOffer] = Field(default_factory=list)
    image_url: str | None = None  # a path on the ordering server, for the kiosk screen only


class Outlet(BaseModel):
    """Who the outlet is (GET /outlets/{code}): its code, name and address."""

    code: str
    name: str
    address: str


class MenuCategory(BaseModel):
    """A menu section. `slug` is what a dish's `category` holds."""

    slug: str
    name: str


class MenuCatalog(BaseModel):
    """The outlet's whole menu (GET /catalog). `version` changes whenever anything in it does."""

    version: str
    categories: list[MenuCategory] = Field(default_factory=list)
    dishes: list[MenuDish] = Field(alias="products")
