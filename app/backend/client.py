"""The only code that talks HTTP to the restaurant backend."""

import json
from typing import Any, NamedTuple

import httpx

from app.backend.errors import (
    BackendConflict,
    BackendError,
    BackendNotFound,
    BackendRuleViolation,
    BackendUnavailable,
)
from app.backend.models import (
    Customer,
    DriveThruOrder,
    Favourite,
    MenuCatalog,
    Outlet,
)


class _Refusal(NamedTuple):
    """An error response, read: the text for the model and what the server said in full."""

    message: str
    code: str | None
    missing: list[dict[str, Any]]
    problems: list[dict[str, Any]]


def _refusal(response: httpx.Response) -> _Refusal:
    """The server's error as `{"detail": {"code", "message", ...}}`. The text is the message, and
    for a cart the messages of what is missing or wrong, without the ids and indexes. Anything
    else (a plain string, FastAPI's own field errors, no JSON) is passed on as it came."""
    try:
        detail = response.json().get("detail")
    except ValueError, AttributeError:
        detail = None
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        missing, problems = detail.get("missing") or [], detail.get("problems") or []
        issues = [i["message"] for i in [*missing, *problems] if i.get("message")]
        text = detail["message"] + (": " + "; ".join(issues) if issues else "")
        return _Refusal(text, detail.get("code"), missing, problems)
    if isinstance(detail, str):
        text = detail
    elif detail is not None:
        text = json.dumps(detail, separators=(",", ":"))
    else:
        text = response.text or f"HTTP {response.status_code}"
    return _Refusal(text, None, [], [])


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
            raise BackendUnavailable(
                _refusal(response).message, status, may_have_been_processed=True
            )
        if status >= 400:
            r = _refusal(response)
            error = (
                BackendNotFound
                if status == 404
                else BackendConflict
                if status == 409
                else BackendRuleViolation
            )
            raise error(r.message, status, code=r.code, missing=r.missing, problems=r.problems)
        if status == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise BackendError("Backend returned invalid JSON", status) from exc

    def get_customer(self, customer_id: int) -> Customer:
        """GET /customers/{id}."""
        return Customer.model_validate(self._request("GET", f"/customers/{customer_id}"))

    def patch_preferences(self, customer_id: int, preferences: dict[str, Any]) -> Customer:
        """PATCH /customers/{id}/preferences. The backend merges shallowly, so callers
        send every top-level key they want to keep."""
        body = {"preferences": preferences}
        data = self._request("PATCH", f"/customers/{customer_id}/preferences", body=body)
        return Customer.model_validate(data)

    def create_order(self, outlet_code: str, customer_id: int | None = None) -> DriveThruOrder:
        """POST /orders: start an empty draft order, for a customer if one is known."""
        body: dict[str, Any] = {"outlet": outlet_code}
        if customer_id is not None:
            body["customer_id"] = customer_id
        return DriveThruOrder.model_validate(self._request("POST", "/orders", body=body))

    def get_order(self, order_id: int) -> DriveThruOrder:
        """GET /orders/{id}: the order as it stands, whatever its status."""
        return DriveThruOrder.model_validate(self._request("GET", f"/orders/{order_id}"))

    def cancel_order(self, order_id: int) -> DriveThruOrder:
        """DELETE /orders/{id}: abandon a draft. Safe to repeat; a placed order is a conflict."""
        return DriveThruOrder.model_validate(self._request("DELETE", f"/orders/{order_id}"))

    def set_line_quantity(self, order_id: int, line_id: int, quantity: int) -> DriveThruOrder:
        """PATCH /orders/{id}/lines/{line_id}: change how many; the line keeps its id."""
        body = {"quantity": quantity}
        path = f"/orders/{order_id}/lines/{line_id}"
        return DriveThruOrder.model_validate(self._request("PATCH", path, body=body))

    def attach_customer(self, order_id: int, customer_id: int) -> DriveThruOrder:
        """PUT /orders/{id}/customer: put a draft on a customer identified after it began."""
        body = {"customer_id": customer_id}
        path = f"/orders/{order_id}/customer"
        return DriveThruOrder.model_validate(self._request("PUT", path, body=body))

    def find_or_add_customer(self, phone: str) -> Customer:
        """POST /customers: the customer with this mobile number, added if new. Only the number
        is needed; the server accepts the usual ways of writing it."""
        return Customer.model_validate(self._request("POST", "/customers", body={"phone": phone}))

    def get_favourites(self, customer_id: int, limit: int = 5) -> list[Favourite]:
        """GET /customers/{id}/favourites: what they order most, still on the menu."""
        data = self._request("GET", f"/customers/{customer_id}/favourites", params={"limit": limit})
        return [Favourite.model_validate(f) for f in data]

    def add_order_line(self, order_id: int, line: dict[str, Any]) -> DriveThruOrder:
        """POST /orders/{id}/lines. A 422 carries `missing` and `problems` in its message."""
        data = self._request("POST", f"/orders/{order_id}/lines", body=line)
        return DriveThruOrder.model_validate(data)

    def remove_order_line(self, order_id: int, line_id: int) -> DriveThruOrder:
        """DELETE /orders/{id}/lines/{line_id}."""
        data = self._request("DELETE", f"/orders/{order_id}/lines/{line_id}")
        return DriveThruOrder.model_validate(data)

    def confirm_order(self, order_id: int) -> DriveThruOrder:
        """POST /orders/{id}/confirm: freeze the draft and give it its number."""
        return DriveThruOrder.model_validate(self._request("POST", f"/orders/{order_id}/confirm"))

    def get_outlet(self, outlet_code: str) -> Outlet:
        """GET /outlets/{code}: the outlet's name and address."""
        return Outlet.model_validate(self._request("GET", f"/outlets/{outlet_code}"))

    def get_catalog_version(self, outlet_code: str) -> str:
        """GET /catalog/version: changes whenever the outlet's menu does."""
        data = self._request("GET", "/catalog/version", params={"outlet": outlet_code})
        return str(data["version"])

    def get_catalog(self, outlet_code: str) -> MenuCatalog:
        """GET /catalog: what this outlet is selling now, every dish with its questions, meals,
        nutrition and allergens, and the menu's version."""
        data = self._request("GET", "/catalog", params={"outlet": outlet_code})
        return MenuCatalog.model_validate(data)
