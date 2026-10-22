"""A stand-in for the ordering server that keeps one draft the way the real one does."""

import json
from typing import Any

import httpx


def refusal(status: int, code: str, message: str, **lists: Any) -> httpx.Response:
    """An error the way the ordering server sends it: `detail` has a `code` and a `message`."""
    return httpx.Response(status, json={"detail": {"code": code, "message": message, **lists}})


MENU = {4: ("McAloo Tikki", 76.19), 5: ("McSpicy Chicken", 263.81), 6: ("Float", 90.0)}
REQUIRED = {5: (2, "McSpicy Chicken: Sauce"), 6: (20, "Float: Flavour")}  # dish -> its question


def _option(i: int, name: str, price: float = 0, default: bool = False) -> dict[str, Any]:
    return {"id": i, "name": name, "price_delta": price, "is_default": default}


def _group(i: int, name: str, low: int, options: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": i, "name": name, "min_select": low, "max_select": max(low, 1), "options": options}


CATEGORIES = [
    {"id": 1, "slug": "burgers", "name": "Burgers"},
    {"id": 2, "slug": "desserts", "name": "Desserts"},
]

# What GET /products and GET /products/{id} say about those two dishes.
PRODUCTS: dict[int, dict[str, Any]] = {
    4: {"id": 4, "name": "McAloo Tikki Burger ®", "kind": "item", "veg": "veg",
        "category": "burgers", "base_price": 76.19, "image_url": "/images/4.png",
        "nutrition": {"calories_kcal": 339, "protein_g": 8.5, "fat_g": 13.0, "carbs_g": 48.0,
                      "sugar_g": 6.0, "sodium_mg": 560},
        "allergens": ["gluten", "soy"],
        "option_groups": [
            _group(1, "Sauce", 1,
                   [_option(1, "Complimentary Ketchup", default=True), _option(2, "No Ketchup")]),
            _group(3, "Cheese", 0,
                   [_option(4, "Cheese", 28.57), _option(5, "Double Cheese", 58.1)]),
        ],
        "meal_offers": [
            {"size": "Medium", "price_delta": 148.57,
             "side": _group(10, "Meal side (Medium)", 1, [_option(20, "Medium Fries")]),
             "drink": _group(11, "Meal drink (Medium)", 1,
                             [_option(30, "Medium Coke"), _option(31, "Coke Zero"),
                              _option(32, "Coke Zero Can")])},
            {"size": "Large", "price_delta": 176.19, "side": None,
             "drink": _group(12, "Meal drink (Large)", 1, [_option(40, "Large Coke")])},
        ]},
    6: {"id": 6, "name": "Float", "kind": "item", "veg": "veg", "category": "desserts",
        "base_price": 90.0, "meal_offers": [],
        "option_groups": [_group(20, "Flavour", 1,
                                 [_option(60 + n, f"Flavour {n}") for n in range(9)]
                                 + [_option(70, "Cola Float", 10)])]},
    5: {"id": 5, "name": "McSpicy Chicken", "kind": "item", "veg": "non_veg",
        "category": "burgers", "base_price": 263.81, "meal_offers": [],
        "option_groups": [_group(2, "Sauce", 1, [_option(7, "Tomato Ketchup"),
                                                 _option(8, "No Sauce")])]},
}  # fmt: skip


class FakeOrderServer:
    """Keeps one draft the way the ordering server does."""

    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self.status = "draft"
        self.number: int | None = None
        self.next_item_id = 10
        self.created_with: dict[str, Any] = {}
        self.sent: dict[str, Any] = {}  # the last item the tool asked to add
        self.customer_id: int | None = None
        self.lose_next_reply = False
        self.menu_version = "v1"
        self.preferences: dict[str, Any] = {}  # what the customer record holds
        self.favourites: list[dict[str, Any]] = []
        self.customer_known = False
        self.next_name: str | None = None  # what the server calls the next line it adds
        self.refuse_add: tuple[str, str] | None = None  # (problem code, message) for the next add
        self.price_changed = False  # when set, confirming is refused the way the server does

    def order(self) -> dict[str, Any]:
        subtotal = round(sum(x["line_total"] for x in self.lines), 2)
        gst = round(subtotal * 0.05, 2)
        return {
            "id": 7,
            "status": self.status,
            "customer_id": self.customer_id,
            "order_number": self.number,
            "lines": self.lines,
            "subtotal": subtotal,
            "gst": gst,
            "total": round(subtotal + gst, 2),
        }

    def confirm(self) -> httpx.Response:
        if not self.lines:
            return refusal(409, "empty_order", "The order has no items")
        if self.status != "draft":
            return refusal(409, "order_closed", f"Order 7 is already {self.status}")
        if self.price_changed:
            for line in self.lines:  # the server re-prices the lines when it refuses
                line["line_total"] = round(line["line_total"] + 10, 2)
            problem = {"line": 0, "code": "price_changed", "message": "McAloo Tikki is now 80"}
            return refusal(
                409, "cannot_confirm", "The order cannot be placed as it is",
                missing=[], problems=[problem],
            )  # fmt: skip
        self.status, self.number = "confirmed", 14
        return httpx.Response(200, json=self.order())

    def handle(self, request: httpx.Request) -> httpx.Response:
        response = self._serve(request)
        if self.lose_next_reply:  # the server did it, but the answer never arrived
            self.lose_next_reply = False
            raise httpx.ReadTimeout("reply lost", request=request)
        return response

    def _serve(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/catalog/version":
            return httpx.Response(200, json={"version": self.menu_version})
        if request.method == "GET" and request.url.path == "/catalog":
            return httpx.Response(
                200,
                json={
                    "version": self.menu_version,
                    "categories": CATEGORIES,
                    "products": list(PRODUCTS.values()),
                },
            )
        parts = request.url.path.strip("/").split("/")
        if parts == ["customers"] and request.method == "POST":
            digits = "".join(c for c in json.loads(request.content)["phone"] if c.isdigit())
            digits = digits[2:] if len(digits) == 12 and digits.startswith("91") else digits
            if len(digits) != 10 or digits[0] not in "6789":
                msg = "Value error, Enter a 10 digit Indian mobile number"
                detail = [{"loc": ["body", "phone"], "type": "value_error", "msg": msg}]
                return httpx.Response(422, json={"detail": detail})
            known, self.customer_known = self.customer_known, True
            body = {
                "id": 3, "phone": "+91" + digits, "name": None, "email": None,
                "preferences": self.preferences, "created_at": "2030-06-01T12:00:00Z",
            }  # fmt: skip
            return httpx.Response(200 if known else 201, json=body)
        if parts[:1] == ["customers"] and parts[2:] == ["preferences"]:
            self.preferences.update(json.loads(request.content)["preferences"])  # shallow merge
            body = {
                "id": int(parts[1]), "phone": "+919876543210", "name": None, "email": None,
                "preferences": self.preferences, "created_at": "2030-06-01T12:00:00Z",
            }  # fmt: skip
            return httpx.Response(200, json=body)
        if parts[:1] == ["customers"] and parts[2:] == ["favourites"]:
            return httpx.Response(200, json=self.favourites)
        changes_lines = len(parts) >= 3 and parts[2] == "lines"
        if changes_lines and self.status != "draft":
            return refusal(409, "order_closed", f"Order 7 is already {self.status}")
        if parts[0] == "orders" and len(parts) == 2:
            if request.method == "GET":
                return httpx.Response(200, json=self.order())
            if request.method == "DELETE":  # cancel
                if self.status == "confirmed":
                    return refusal(409, "order_closed", "Order 7 is already confirmed")
                self.status = "cancelled"
                return httpx.Response(200, json=self.order())
        if parts[0] == "orders" and len(parts) == 3 and parts[2] == "customer":
            self.customer_id = json.loads(request.content)["customer_id"]
            return httpx.Response(200, json=self.order())
        if request.method == "PATCH" and len(parts) == 4:
            line = next((x for x in self.lines if x["id"] == int(parts[3])), None)
            if line is None:
                return refusal(404, "not_found", f"Order 7 has no line {parts[3]}")
            unit = line["line_total"] / line["quantity"]
            line["quantity"] = json.loads(request.content)["quantity"]
            line["line_total"] = round(unit * line["quantity"], 2)
            return httpx.Response(200, json=self.order())
        if request.url.path == "/orders":
            self.created_with = json.loads(request.content)
            self.lines, self.status, self.number = [], "draft", None  # a new, empty draft
            return httpx.Response(201, json=self.order())
        if request.url.path.endswith("/confirm"):
            return self.confirm()
        if request.method == "DELETE":
            dish_id = int(request.url.path.rsplit("/", 1)[1])
            if all(x["id"] != dish_id for x in self.lines):
                return refusal(404, "not_found", f"Order 7 has no line {dish_id}")
            self.lines = [x for x in self.lines if x["id"] != dish_id]
            return httpx.Response(200, json=self.order())
        body = json.loads(request.content)
        self.sent = body
        if self.refuse_add:
            code, message = self.refuse_add
            problem = {"line": 0, "code": code, "message": message}
            return refusal(
                422, "invalid_line", "The item is incomplete or not valid",
                missing=[], problems=[problem],
            )  # fmt: skip
        if body["product_id"] in REQUIRED and not body["options"]:
            group_id, label = REQUIRED[body["product_id"]]
            need = {"line": 0, "code": "required", "group_id": group_id,
                    "message": f"{label} still needs 1 choice"}  # fmt: skip
            return refusal(
                422, "invalid_line", "The item is incomplete or not valid",
                missing=[need], problems=[],
            )  # fmt: skip
        name, price = MENU[body["product_id"]]
        self.lines.append(
            {
                "id": self.next_item_id,
                "product_id": body["product_id"],
                "name": self.next_name or name,
                "quantity": body["quantity"],
                "meal_size": body["meal_size"],
                "note": body["note"],
                "options": [{"name": "Ketchup", "qty": o["qty"]} for o in body["options"]],
                "line_total": round(price * body["quantity"], 2),
            }
        )
        self.next_item_id += 1
        return httpx.Response(201, json=self.order())
