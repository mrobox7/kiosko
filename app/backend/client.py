"""The only code that talks HTTP to the restaurant backend."""

import json
from datetime import datetime
from typing import Any

import httpx

from app.backend.errors import (
    BackendConflict,
    BackendError,
    BackendNotFound,
    BackendRuleViolation,
    BackendUnavailable,
)
from app.backend.models import (
    Availability,
    Customer,
    MenuFilters,
    MenuItem,
    Order,
    Reservation,
)


def _error_message(response: httpx.Response) -> str:
    """The backend's `detail` text, or the raw body when it has no usable detail."""
    try:
        detail = response.json().get("detail")
    except ValueError, AttributeError:
        detail = None
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return json.dumps(detail, separators=(",", ":"))
    return response.text or f"HTTP {response.status_code}"


class BackendClient:
    """Typed calls to the restaurant API. The httpx client is injected."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._http.request(method, path, params=params, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise BackendUnavailable(f"Cannot reach the backend: {exc}") from exc
        except httpx.TransportError as exc:
            raise BackendUnavailable(
                f"Backend request failed: {exc}", may_have_been_processed=True
            ) from exc

        status = response.status_code
        if status >= 500:
            raise BackendUnavailable(_error_message(response), status, may_have_been_processed=True)
        if status >= 400:
            message = _error_message(response)
            if status == 404:
                raise BackendNotFound(message, status)
            if status == 409:
                raise BackendConflict(message, status)
            raise BackendRuleViolation(message, status)
        if status == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise BackendError("Backend returned invalid JSON", status) from exc

    def get_menu(self, filters: MenuFilters | None = None) -> list[MenuItem]:
        """GET /menu."""
        f = filters or MenuFilters()
        params = f.model_dump(exclude_none=True)
        params = {k: v for k, v in params.items() if v != []}
        items = self._request("GET", "/menu", params=params)
        return [MenuItem.model_validate(item) for item in items]

    def get_availability(
        self, slot: datetime, party_size: int, location: str | None = None
    ) -> Availability:
        """GET /availability."""
        params: dict[str, Any] = {"slot_datetime": slot.isoformat(), "party_size": party_size}
        if location:
            params["location"] = location
        return Availability.model_validate(self._request("GET", "/availability", params=params))

    def lookup_customer(self, *, phone: str | None = None, email: str | None = None) -> Customer:
        """GET /customers/lookup. Raises BackendNotFound when nobody matches."""
        params = {k: v for k, v in {"phone": phone, "email": email}.items() if v}
        return Customer.model_validate(self._request("GET", "/customers/lookup", params=params))

    def create_customer(
        self, name: str, phone: str | None = None, email: str | None = None
    ) -> Customer:
        """POST /customers."""
        body = {"name": name, "phone": phone, "email": email}
        return Customer.model_validate(self._request("POST", "/customers", body=body))

    def create_reservation(
        self, customer_id: int, table_id: int, slot: datetime, party_size: int
    ) -> Reservation:
        """POST /reservations."""
        body = {
            "customer_id": customer_id,
            "table_id": table_id,
            "slot_datetime": slot.isoformat(),
            "party_size": party_size,
        }
        return Reservation.model_validate(self._request("POST", "/reservations", body=body))

    def get_reservation(self, reservation_id: int) -> Reservation:
        """GET /reservations/{id}."""
        return Reservation.model_validate(self._request("GET", f"/reservations/{reservation_id}"))

    def list_customer_reservations(
        self, customer_id: int, status: str | None = None
    ) -> list[Reservation]:
        """GET /customers/{id}/reservations."""
        params = {"status": status} if status else None
        data = self._request("GET", f"/customers/{customer_id}/reservations", params=params)
        return [Reservation.model_validate(r) for r in data]

    def cancel_reservation(self, reservation_id: int) -> Reservation:
        """DELETE /reservations/{id}."""
        data = self._request("DELETE", f"/reservations/{reservation_id}")
        return Reservation.model_validate(data)

    def add_order(self, reservation_id: int, menu_item_id: int, quantity: int) -> Order:
        """POST /reservations/{id}/orders."""
        body = {"menu_item_id": menu_item_id, "quantity": quantity}
        data = self._request("POST", f"/reservations/{reservation_id}/orders", body=body)
        return Order.model_validate(data)

    def list_reservation_orders(self, reservation_id: int) -> list[Order]:
        """GET /reservations/{id}/orders."""
        data = self._request("GET", f"/reservations/{reservation_id}/orders")
        return [Order.model_validate(o) for o in data]

    def list_customer_orders(self, customer_id: int) -> list[Order]:
        """GET /customers/{id}/orders."""
        data = self._request("GET", f"/customers/{customer_id}/orders")
        return [Order.model_validate(o) for o in data]

    def delete_order(self, order_id: int) -> None:
        """DELETE /orders/{id}."""
        self._request("DELETE", f"/orders/{order_id}")

    def get_customer(self, customer_id: int) -> Customer:
        """GET /customers/{id}."""
        return Customer.model_validate(self._request("GET", f"/customers/{customer_id}"))

    def patch_preferences(self, customer_id: int, preferences: dict[str, Any]) -> Customer:
        """PATCH /customers/{id}/preferences. The backend merges shallowly, so callers
        send every top-level key they want to keep."""
        body = {"preferences": preferences}
        data = self._request("PATCH", f"/customers/{customer_id}/preferences", body=body)
        return Customer.model_validate(data)

    def get_menu_item(self, item_id: int) -> MenuItem:
        """GET /menu/{id}."""
        return MenuItem.model_validate(self._request("GET", f"/menu/{item_id}"))
