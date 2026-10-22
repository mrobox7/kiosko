"""The menu the agent holds: how the outline is written and when the menu is reloaded."""

import httpx
import pytest

from app.backend.client import BackendClient
from app.backend.errors import BackendUnavailable
from app.backend.models import MenuDish
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.menu.menu import Menu
from app.menu.outline import render_outline
from app.session.factory import Runtime
from app.session.prompts import MENU_HEADING, STABLE_PROMPT, system_prompt
from tests.support.builders import OUTLET_INFO, clock, make_ctx, make_loop
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


def dishes(raw: list[dict]) -> list[MenuDish]:
    return [MenuDish.model_validate(d) for d in raw]


def test_the_outline_has_a_line_per_category_in_menu_order() -> None:
    assert render_outline(dishes(MENU)) == "\n".join(
        [
            "burgers: McAloo Tikki Burger, McVeggie",
            "fries-sides: Fries",
            "meals: Spicy Paneer/Spicy Chicken Burger",
            "mccaf: Velvety Chocolate Cup",
            "beverages: Coke, Coke Zero",
        ]
    )


def test_an_empty_menu_gives_an_empty_outline() -> None:
    assert render_outline([]) == ""


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
    first = menu.outline
    menu.refresh()
    menu.refresh()
    assert menu.outline == first
    assert server.asked == ["/catalog/version", "/catalog", "/catalog/version", "/catalog/version"]


def test_a_new_menu_version_reloads_the_menu_and_its_outline() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    menu.refresh()
    assert "Coke Zero" in menu.outline
    server.version, server.menu = "v2", [d for d in MENU if "Zero" not in d["name"]]
    menu.refresh()
    assert "Coke Zero" not in menu.outline
    assert server.asked.count("/catalog") == 2


def test_reading_the_menu_makes_no_request_once_it_is_held() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    menu.refresh()
    server.asked.clear()
    assert [d.name for d in menu.dishes][:2] == ["McAloo Tikki Burger ®", "McVeggie®"]
    found = menu.dish(2)
    assert found is not None and found.name == "McVeggie®" and menu.dish(999) is None
    assert menu.outline and server.asked == []


def test_the_first_read_loads_the_menu_without_being_told_to() -> None:
    server = Server()
    menu = Menu(server.client, "JPR-013-7429")
    assert any(d.name == "Coke" for d in menu.dishes)
    assert server.asked == ["/catalog/version", "/catalog"]


def test_the_dishes_follow_the_outline_when_the_menu_changes() -> None:
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
    kept = menu.outline
    server.down = True
    menu.refresh()
    assert menu.outline == kept and menu.dish(6) is not None


def test_without_a_first_menu_a_backend_failure_is_raised() -> None:
    server = Server()
    server.down = True
    with pytest.raises(BackendUnavailable):
        Menu(server.client, "JPR-013-7429").refresh()


# --- in the system prompt


def test_the_system_prompt_without_an_outline_is_unchanged() -> None:
    assert system_prompt() == STABLE_PROMPT


def test_the_outline_comes_last_in_the_fixed_system_message() -> None:
    outline = "burgers: McVeggie"
    assert system_prompt(outline) == f"{STABLE_PROMPT}\n\n{MENU_HEADING}\n{outline}"


def test_each_new_chat_gets_the_outline_current_at_that_moment() -> None:
    server = Server()
    llm = FakeLLM([LLMResponse(text="ok"), LLMResponse(text="ok")])
    runtime = Runtime(
        backend=make_ctx(FakeOrderServer()).backend,
        loop=make_loop(llm),
        clock=clock,
        menu=Menu(server.client, "JPR-013-7429"),
        outlet=OUTLET_INFO,
    )
    runtime.start_session().send("hi")
    server.version, server.menu = "v2", [dish("Latte", "mccaf", 1)]
    runtime.start_session().send("hi")
    first, second = (call.system for call in llm.calls)
    assert "McAloo Tikki Burger" in first and "Latte" not in first
    assert "Latte" in second and "McAloo" not in second
