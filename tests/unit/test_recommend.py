"""recommend_items: filtering by saved preferences, ranking by order history."""

import pytest

from app.domain.results import ToolResult
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx
from tests.support.fake_backend import MENU, FakeBackend

REG = ToolRegistry.discover()
SLOT = "2030-06-10T19:30:00"
BY_ID = {m["id"]: m for m in MENU}


def recommend(backend: FakeBackend, customer_id: int) -> ToolResult:
    return REG.dispatch("recommend_items", {}, make_ctx(backend, customer_id))


def ids(r: ToolResult) -> list[int]:
    return [s["id"] for s in r.data["suggestions"]]


def test_vegetarian_customer_only_gets_vegetarian_dishes() -> None:
    r = recommend(FakeBackend(), 1)  # Priya: vegetarian
    assert r.ok and len(ids(r)) == 3
    assert all("vegetarian" in BY_ID[i]["tags"] for i in ids(r))


def test_nut_allergy_excludes_nut_dishes() -> None:
    r = recommend(FakeBackend(), 3)  # Anita: nuts
    assert r.ok and all("contains-nuts" not in BY_ID[i]["tags"] for i in ids(r))


def test_new_dishes_come_from_different_sections() -> None:
    r = recommend(FakeBackend(), 2)  # Rahul: no preferences, no orders
    assert len({s["category"] for s in r.data["suggestions"]}) == 3
    assert {s["reason"] for s in r.data["suggestions"]} == {"new to you"}


def test_dishes_ordered_before_come_first_most_ordered_first() -> None:
    b = FakeBackend()
    rid = b.add_reservation(2, 7, SLOT)
    for item, qty in ((4, 1), (8, 3)):  # Samosa x1, Veg Biryani x3
        REG.dispatch(
            "add_order_items",
            {"reservation_id": rid, "items": [{"menu_item_id": item, "quantity": qty}]},
            make_ctx(b, 2),
        )
    r = recommend(b, 2)
    assert ids(r)[:2] == [8, 4]
    assert r.data["suggestions"][0]["reason"] == "ordered 3x before"


def test_allergy_without_a_menu_tag_is_flagged_not_filtered() -> None:
    b = FakeBackend()
    REG.dispatch("update_preferences", {"allergies_add": ["soy"]}, make_ctx(b, 2))
    r = recommend(b, 2)
    assert r.ok and r.data["unchecked_allergies"] == ["soy"] and r.data["suggestions"]


def test_vegan_with_nut_and_dairy_allergies_gets_only_safe_dishes() -> None:
    b = FakeBackend()
    REG.dispatch(
        "update_preferences",
        {"dietary_add": ["vegan"], "allergies_add": ["nuts", "dairy"]},
        make_ctx(b, 2),
    )
    r = recommend(b, 2)
    assert (
        r.ok
        and r.data["suggestions"]
        and all({"contains-nuts", "contains-dairy"}.isdisjoint(BY_ID[i]["tags"]) for i in ids(r))
    )


def test_nothing_on_the_menu_gives_empty_list_and_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = make_ctx(FakeBackend(), 2)
    monkeypatch.setattr(ctx.backend, "get_menu", lambda filters=None: [])
    r = REG.dispatch("recommend_items", {}, ctx)
    assert r.ok and r.data["suggestions"] == [] and "No available dish" in r.data["note"]


def test_compact_line() -> None:
    r = ToolResult.success({"suggestions": [{"id": 1, "name": "Paneer Tikka"}]})
    assert REG.compact("recommend_items", {}, r) == "suggested: #1 Paneer Tikka"
    empty = ToolResult.success({"suggestions": []})
    assert REG.compact("recommend_items", {}, empty) == "no suggestions"
