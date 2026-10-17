"""Fake restaurant backend on an httpx mock transport, seeded from tests/fixtures."""

import json
from pathlib import Path

import httpx

from app.backend.client import BackendClient

MENU = json.loads((Path(__file__).parent.parent / "fixtures" / "menu.json").read_text())


def _menu_route(request: httpx.Request) -> httpx.Response:
    q = request.url.params
    items = MENU
    if q.get("available_only", "true") == "true":
        items = [i for i in items if i["available"]]
    if cat := q.get("category"):
        items = [i for i in items if i["category"] == cat]
    if mp := q.get("max_price"):
        items = [i for i in items if i["price"] <= float(mp)]
    if any_ := q.get_list("tags_any"):
        items = [i for i in items if set(any_) & set(i["tags"])]
    if all_ := q.get_list("tags_all"):
        items = [i for i in items if set(all_) <= set(i["tags"])]
    if ex := q.get_list("exclude_tags"):
        items = [i for i in items if not set(ex) & set(i["tags"])]
    return httpx.Response(200, json=items)


class FakeBackend:
    """Route table plus a record of every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.client = BackendClient(
            httpx.Client(base_url="http://test", transport=httpx.MockTransport(self._handle))
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/menu":
            return _menu_route(request)
        return httpx.Response(404, json={"detail": "Not found"})
