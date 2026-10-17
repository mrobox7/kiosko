"""Argument types and result trimming shared by tools."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator

from app.backend.models import Reservation

Location = Literal["indoor", "outdoor"]


def _naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        raise ValueError("use restaurant local time without a UTC offset, e.g. 2030-06-10T19:30:00")
    return value


LocalDatetime = Annotated[datetime, AfterValidator(_naive)]


def reservation_view(r: Reservation) -> dict[str, Any]:
    """The reservation fields the model needs."""
    return r.model_dump(
        mode="json", include={"id", "table_id", "slot_datetime", "party_size", "status"}
    )
