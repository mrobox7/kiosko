from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MenuItem(BaseModel):
    id: int
    name: str
    description: str
    price: float
    tags: list[str]
    category: str
    available: bool


class MenuFilters(BaseModel):
    category: str | None = None
    tags_any: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    max_price: float | None = None
    available_only: bool = True


class Customer(BaseModel):
    """CustomerOut."""

    id: int
    name: str
    phone: str | None
    email: str | None
    preferences: dict[str, Any] = Field(default_factory=dict)


class Reservation(BaseModel):
    """ReservationOut."""

    id: int
    customer_id: int
    table_id: int
    slot_datetime: datetime
    party_size: int
    special_requests: str | None = None
    status: str


class Order(BaseModel):
    """OrderOut."""

    id: int
    reservation_id: int
    menu_item_id: int
    quantity: int


class AvailableTable(BaseModel):
    """AvailableTable."""

    table_id: int
    table_number: int
    capacity: int
    location: str


class Availability(BaseModel):
    """AvailabilityOut."""

    slot_datetime: datetime
    party_size: int
    available_tables: list[AvailableTable]
