"""Stateful fake restaurant backend on an httpx mock transport.

Mirrors the real API's behaviour recorded in docs/backend-contract.md (status codes and
messages), seeded from tests/fixtures. Records every request."""

import copy
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.backend.client import BackendClient

MENU = json.loads((Path(__file__).parent.parent / "fixtures" / "menu.json").read_text())
FAKE_NOW = datetime(2030, 6, 1, 12, 0)
# (id, capacity, location)
TABLES = [(1, 2, "indoor"), (2, 2, "indoor"), (3, 4, "indoor"), (4, 4, "indoor"),
          (5, 6, "indoor"), (6, 2, "outdoor"), (7, 4, "outdoor"), (8, 8, "outdoor")]  # fmt: skip
CUSTOMERS = [
    {"id": 1, "name": "Priya Sharma", "phone": "+91-9876543210",
     "email": "priya.sharma@example.com",
     "preferences": {"seating": "outdoor", "dietary": ["vegetarian"]}},
    {"id": 2, "name": "Rahul Verma", "phone": "+91-9876543211",
     "email": "rahul.v@example.com", "preferences": {}},
    {"id": 3, "name": "Anita Iyer", "phone": "+91-9876543212",
     "email": "anita.iyer@example.com", "preferences": {"allergies": ["nuts"]}},
]  # fmt: skip


def _detail(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"detail": message})


def _menu(q: httpx.QueryParams) -> httpx.Response:
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
    """Route table, in-memory state and a record of every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.customers: list[dict[str, Any]] = copy.deepcopy(CUSTOMERS)
        self.reservations: dict[int, dict[str, Any]] = {}
        self.orders: dict[int, dict[str, Any]] = {}
        # Test hook: (method, path regex) -> response, consulted before the normal routes.
        self.overrides: list[tuple[str, str, Callable[[httpx.Request], httpx.Response]]] = []
        self.client = BackendClient(
            httpx.Client(base_url="http://test", transport=httpx.MockTransport(self._handle))
        )

    # -- helpers for tests ------------------------------------------------------------
    def add_reservation(self, customer_id: int, table_id: int, slot: str, party: int = 2) -> int:
        rid = len(self.reservations) + 1
        self.reservations[rid] = {
            "id": rid, "customer_id": customer_id, "table_id": table_id,
            "slot_datetime": slot, "party_size": party, "special_requests": None,
            "status": "confirmed",
        }  # fmt: skip
        return rid

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

    # -- routing ----------------------------------------------------------------------
    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for method, pattern, fn in self.overrides:
            if request.method == method and re.fullmatch(pattern, request.url.path):
                return fn(request)
        path, method, q = request.url.path, request.method, request.url.params
        body = json.loads(request.content) if request.content else {}

        if path == "/menu":
            return _menu(q)
        if m := re.fullmatch(r"/menu/(\d+)", path):
            item = next((i for i in MENU if i["id"] == int(m[1])), None)
            return httpx.Response(200, json=item) if item else _detail(404, "Menu item not found")
        if m := re.fullmatch(r"/customers/(\d+)", path):
            c = next((c for c in self.customers if c["id"] == int(m[1])), None)
            return httpx.Response(200, json=c) if c else _detail(404, "Customer not found")
        if m := re.fullmatch(r"/customers/(\d+)/preferences", path) and method == "PATCH":
            c = next((c for c in self.customers if c["id"] == int(path.split("/")[2])), None)
            if c is None:
                return _detail(404, "Customer not found")
            c["preferences"] = {**c["preferences"], **body["preferences"]}  # shallow, like the API
            return httpx.Response(200, json=c)
        if path == "/customers/lookup":
            return self._lookup(q)
        if path == "/customers" and method == "POST":
            return self._create_customer(body)
        if path == "/availability":
            return self._availability(q)
        if path == "/reservations" and method == "POST":
            return self._create_reservation(body)
        if m := re.fullmatch(r"/customers/(\d+)/reservations", path):
            rows = [r for r in self.reservations.values() if r["customer_id"] == int(m[1])]
            if status := q.get("status"):
                rows = [r for r in rows if r["status"] == status]
            return httpx.Response(200, json=rows)
        if m := re.fullmatch(r"/customers/(\d+)/orders", path):
            mine = {r["id"] for r in self.reservations.values() if r["customer_id"] == int(m[1])}
            return httpx.Response(
                200, json=[o for o in self.orders.values() if o["reservation_id"] in mine]
            )
        if m := re.fullmatch(r"/reservations/(\d+)", path):
            return self._reservation(method, int(m[1]))
        if m := re.fullmatch(r"/reservations/(\d+)/orders", path):
            return self._reservation_orders(method, int(m[1]), body)
        if m := re.fullmatch(r"/orders/(\d+)", path) and method == "DELETE":
            oid = int(path.rsplit("/", 1)[1])
            if self.orders.pop(oid, None) is None:
                return _detail(404, "Order item not found")
            return httpx.Response(204)
        return _detail(404, "Not found")

    def _lookup(self, q: httpx.QueryParams) -> httpx.Response:
        if not q.get("phone") and not q.get("email"):
            return _detail(400, "Provide phone or email")
        for c in self.customers:
            if (q.get("phone") and c["phone"] == q["phone"]) or (
                q.get("email") and c["email"] == q["email"]
            ):
                return httpx.Response(200, json=c)
        return _detail(404, "Customer not found")

    def _create_customer(self, body: dict[str, Any]) -> httpx.Response:
        if not body.get("phone") and not body.get("email"):
            return _detail(422, "At least one of phone or email is required")
        for c in self.customers:
            if (body.get("phone") and c["phone"] == body["phone"]) or (
                body.get("email") and c["email"] == body["email"]
            ):
                return _detail(409, f"Customer already exists with id {c['id']}")
        c = {"id": len(self.customers) + 1, "preferences": {}, **body}
        self.customers.append(c)
        return httpx.Response(201, json=c)

    def _availability(self, q: httpx.QueryParams) -> httpx.Response:
        slot, party = q["slot_datetime"], int(q["party_size"])
        taken = {
            r["table_id"]
            for r in self.reservations.values()
            if r["slot_datetime"] == slot and r["status"] == "confirmed"
        }
        free = [
            {"table_id": t, "table_number": t, "capacity": cap, "location": loc}
            for t, cap, loc in TABLES
            if cap >= party and t not in taken and (not q.get("location") or loc == q["location"])
        ]
        return httpx.Response(
            200, json={"slot_datetime": slot, "party_size": party, "available_tables": free}
        )

    def _create_reservation(self, body: dict[str, Any]) -> httpx.Response:
        slot = datetime.fromisoformat(body["slot_datetime"])
        if (
            slot.minute % 30
            or not (12 <= slot.hour <= 22)
            or (slot.hour == 22 and slot.minute > 30)
        ):
            return _detail(
                422, "slot_datetime must be on a 30-min boundary between 12:00 and 22:30"
            )
        if slot < FAKE_NOW:
            return _detail(422, "Cannot create a reservation in the past")
        cap = next(c for t, c, _ in TABLES if t == body["table_id"])
        if body["party_size"] > cap:
            return _detail(422, f"Party of {body['party_size']} exceeds table capacity {cap}")
        for r in self.reservations.values():
            if (r["table_id"], r["slot_datetime"], r["status"]) == (
                body["table_id"], body["slot_datetime"], "confirmed",
            ):  # fmt: skip
                return _detail(409, f"Table {body['table_id']} is already booked at this slot")
        rid = self.add_reservation(
            body["customer_id"], body["table_id"], body["slot_datetime"], body["party_size"]
        )
        return httpx.Response(201, json=self.reservations[rid])

    def _reservation(self, method: str, rid: int) -> httpx.Response:
        r = self.reservations.get(rid)
        if r is None:
            return _detail(404, "Reservation not found")
        if method == "GET":
            return httpx.Response(200, json=r)
        if r["status"] == "cancelled":
            return _detail(409, "Reservation already cancelled")
        if datetime.fromisoformat(r["slot_datetime"]) - FAKE_NOW < timedelta(hours=2):
            return _detail(409, "Cannot cancel within 2 hours of the reservation")
        r["status"] = "cancelled"
        return httpx.Response(200, json=r)

    def _reservation_orders(self, method: str, rid: int, body: dict[str, Any]) -> httpx.Response:
        r = self.reservations.get(rid)
        if r is None:
            return _detail(404, "Reservation not found")
        if method == "GET":
            return httpx.Response(
                200, json=[o for o in self.orders.values() if o["reservation_id"] == rid]
            )
        if r["status"] == "cancelled":
            return _detail(409, "Cannot order on a cancelled reservation")
        if datetime.fromisoformat(r["slot_datetime"]) < FAKE_NOW:
            return _detail(409, "Cannot modify orders for a past reservation")
        item = next((i for i in MENU if i["id"] == body["menu_item_id"]), None)
        if item is None:
            return _detail(404, "Menu item not found")
        if not item["available"]:
            return _detail(409, f"{item['name']} is not available")
        oid = len(self.orders) + 1
        self.orders[oid] = {
            "id": oid, "reservation_id": rid,
            "menu_item_id": body["menu_item_id"], "quantity": body.get("quantity", 1),
        }  # fmt: skip
        return httpx.Response(201, json=self.orders[oid])
