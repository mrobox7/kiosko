"""The only code that talks HTTP to the restaurant backend."""

import json
from typing import Any

import httpx

from app.backend.errors import (
    BackendConflict,
    BackendError,
    BackendNotFound,
    BackendRuleViolation,
    BackendUnavailable,
)
from app.backend.models import MenuFilters, MenuItem


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

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self._http.request(method, path, params=params)
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
