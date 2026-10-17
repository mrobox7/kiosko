import pytest

from app.session.identification import IdentificationError, identify
from tests.support.fake_backend import FakeBackend


def test_found_by_phone_in_any_format() -> None:
    b = FakeBackend()
    for typed in ("+91-9876543210", "9876543210", "+91 98765 43210", "919876543210"):
        assert identify(b.client, phone=typed).name == "Priya Sharma"
    assert not b.writes()


def test_found_by_email_case_insensitive() -> None:
    assert identify(FakeBackend().client, email=" Rahul.V@Example.com ").id == 2


def test_new_customer_is_created_with_canonical_phone() -> None:
    b = FakeBackend()
    c = identify(b.client, name="Mira", phone="9123456780")
    assert c.id == 4 and c.phone == "+91-9123456780"
    assert identify(b.client, phone="+91-9123456780").id == 4  # now found, not duplicated


def test_new_customer_needs_a_name() -> None:
    b = FakeBackend()
    with pytest.raises(IdentificationError, match="name"):
        identify(b.client, email="new@example.com")
    assert not b.writes()


def test_missing_identifier() -> None:
    with pytest.raises(IdentificationError, match="phone number or an email"):
        identify(FakeBackend().client, name="X")
