"""The menu the agent holds: when it is reloaded and what is kept if the backend is down."""

import httpx
import pytest

from app.agent.graph import build_graph, make_saver
from app.agent.services import Services
from app.backend.client import BackendClient
from app.backend.errors import BackendUnavailable
from app.menu.menu import Menu
from app.runtime import Runtime
from tests.support.builders import OUTLET_INFO, clock, make_ctx, plan, say
from tests.support.fake_llm import FakeLLM
from tests.support.fake_order_server import FakeOrderServer


def dish(name: str, category: str, i: int) -> dict:
    return {"id": i, "name": name, "description": None, "kind": "item", "veg": "veg",
            "category": category, "base_price": 100.0, "tags": []}  # fmt: skip


MENU = [
    dish("McAloo Tikki Burger ®", "burgers", 1),
    dish("McVeggie®", "burgers", 2),
    dish("Fries", "fries-sides", 3),
    dish("Spicy Paneer/Spicy Chicken Burger(Any 2)+1 Med Fries+2 Puff", "meals", 4),
    dish("Velvety Chocolate Cup(HOT)", "mccaf", 5),
    dish("Coke", "beverages", 6),
    dish("Coke ® Zero", "beverages", 7),
    dish("Fries", "fries-sides", 8),  # the same name twice shows once
]


# --- reloading only when the menu changes


class Server:
    """The two menu endpoints, counting how often each is asked."""

    def __init__(self) -> None:
        self.version = "v1"
        self.menu = MENU
        self.down = False
        self.asked: list[str] = []
        http = httpx.Client(base_url="http://shop", transport=httpx.MockTransport(self.handle))
        self.client = BackendClient(http)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.params["outlet"] == "JPR-013-7429"
        self.asked.append(request.url.path)
        if self.down:
            return httpx.Response(503, json={"detail": "down"})
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"version": self.version})
        return httpx.Response(200, json={"version": self.version, "products": self.menu})


def test_the_menu_is_fetched_once_and_only_the_version_is_asked_after() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    menu.refresh()
    first = menu.dishes
    menu.refresh()
    menu.refresh()
    assert menu.dishes == first
    assert server.asked == ["/catalog/version", "/catalog", "/catalog/version", "/catalog/version"]


def test_a_new_menu_version_reloads_the_menu() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    menu.refresh()
    assert any("Zero" in d.name for d in menu.dishes)
    server.version, server.menu = "v2", [d for d in MENU if "Zero" not in d["name"]]
    menu.refresh()
    assert not any("Zero" in d.name for d in menu.dishes)
    assert server.asked.count("/catalog") == 2


def test_reading_the_menu_makes_no_request_once_it_is_held() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    menu.refresh()
    server.asked.clear()
    assert [d.name for d in menu.dishes][:2] == ["McAloo Tikki Burger ®", "McVeggie®"]
    found = menu.dish(2)
    assert found is not None and found.name == "McVeggie®" and menu.dish(999) is None
    assert menu.dishes and server.asked == []


def test_the_first_read_loads_the_menu_without_being_told_to() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    assert any(d.name == "Coke" for d in menu.dishes)
    assert server.asked == ["/catalog/version", "/catalog"]


def test_the_dishes_follow_the_menu_when_it_changes() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    assert any(d.name == "Coke" for d in menu.dishes)
    server.version, server.menu = "v2", [dish("Latte", "mccaf", 1)]
    menu.refresh()
    assert [d.name for d in menu.dishes] == ["Latte"] and menu.dish(6) is None


def test_when_the_backend_cannot_be_asked_the_last_menu_is_kept() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    menu.refresh()
    kept = menu.dishes
    server.down = True
    menu.refresh()
    assert menu.dishes == kept and menu.dish(6) is not None


def test_without_a_first_menu_a_backend_failure_is_raised() -> None:
    server = Server()
    server.down = True
    with pytest.raises(BackendUnavailable):
        Menu(server.client, "JPR-013-7429").refresh()


# --- in the planner's system message


def test_each_new_chat_sees_the_menu_current_at_that_moment() -> None:
    server = Server()
    llm = FakeLLM([plan({"type": "chat"}), say("Hi.")])
    services = Services(
        backend=make_ctx(FakeOrderServer()).backend,
        menu=Menu(server.client, "JPR-013-7429"),
        llm=llm,
        clock=clock,
        outlet=OUTLET_INFO,
    )
    saver = make_saver()
    runtime = Runtime(services=services, graph=build_graph(services, saver), saver=saver)
    runtime.start_session()
    server.version, server.menu = "v2", [dish("Latte", "mccaf", 1)]
    second = runtime.start_session()  # reloads the menu before this customer starts
    second.send("hi")
    card = llm.calls[0].system  # what the first model call was told about the menu
    assert "Latte" in card and "McAloo" not in card
