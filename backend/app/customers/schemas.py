"""What the customer endpoints accept and send."""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_MOBILE = re.compile(r"(?:\+?91|0)?([6-9]\d{9})")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class CustomerCreate(BaseModel):
    phone: str  # an Indian mobile number; stored as +91 and ten digits
    name: str | None = Field(default=None, max_length=100)
    email: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        match = _MOBILE.fullmatch(re.sub(r"[\s-]", "", value))
        if not match:
            raise ValueError("Enter a 10 digit Indian mobile number")
        return "+91" + match.group(1)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _EMAIL.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value.lower()


class CustomerOut(BaseModel, from_attributes=True):
    id: int
    phone: str
    name: str | None
    email: str | None
    preferences: dict[str, Any]
    created_at: datetime


class PreferencesUpdate(BaseModel):
    preferences: dict[str, Any]


class Favourite(BaseModel):
    """A product this customer has ordered before."""

    product_id: int
    name: str
    times_ordered: int  # in how many confirmed orders
    total_quantity: int
    last_ordered_at: datetime
