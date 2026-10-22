"""Customer table."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    """Someone who gave their mobile number. Orders can be anonymous; this is optional."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # +91 and ten digits
    email: Mapped[str | None] = mapped_column(String(200))
    name: Mapped[str | None] = mapped_column(String(100))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON)  # diet, allergies, anything else
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
