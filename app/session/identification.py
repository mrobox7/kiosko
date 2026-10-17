"""Resolve the customer before chat. Runs in code, never through the LLM."""

import re

from app.backend.client import BackendClient
from app.backend.errors import BackendError, BackendNotFound
from app.backend.models import Customer


class IdentificationError(Exception):
    """Something the customer can fix or must be told. The message is safe to show."""


def _phone_forms(phone: str) -> list[str]:
    """The backend matches phone strings exactly and stores `+91-XXXXXXXXXX`,
    so try the typed form and the canonical form."""
    typed = phone.strip()
    digits = re.sub(r"\D", "", typed)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    canonical = f"+91-{digits}" if len(digits) == 10 else typed
    return list(dict.fromkeys([canonical, typed]))


def identify(
    backend: BackendClient, *, name: str = "", phone: str = "", email: str = ""
) -> Customer:
    """Look the customer up by phone, then email; create them if not found."""
    phone, email, name = phone.strip(), email.strip().lower(), name.strip()
    if not phone and not email:
        raise IdentificationError("Please enter a phone number or an email address.")
    try:
        if phone:
            for form in _phone_forms(phone):
                try:
                    return backend.lookup_customer(phone=form)
                except BackendNotFound:
                    pass
        if email:
            try:
                return backend.lookup_customer(email=email)
            except BackendNotFound:
                pass
        if not name:
            raise IdentificationError("We could not find you. Please enter your name to sign up.")
        return backend.create_customer(
            name, _phone_forms(phone)[0] if phone else None, email or None
        )
    except BackendError as exc:
        raise IdentificationError(f"Sorry, we could not complete sign-in: {exc.message}") from exc
