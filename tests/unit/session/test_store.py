"""Chats that nobody touches are ended: the draft order is cancelled and the chat forgotten."""

import time

import pytest

from app.session.store import SessionStore
from tests.support.builders import make_session, plan, say

IDLE = 180.0
TIKKI = {"type": "add_item", "dish": "McAloo Tikki Burger"}


def store_with_a_draft() -> tuple[SessionStore, str, object]:
    session, _, server = make_session([plan(TIKKI), say("Added.")])
    session.send("one tikki")
    store = SessionStore()
    return store, store.add(session), server


def test_an_idle_chat_is_ended_and_its_draft_cancelled() -> None:
    store, sid, server = store_with_a_draft()
    chat = store.get(sid)
    assert store.sweep(IDLE, now=chat.last_active + IDLE - 1) == []  # not idle long enough yet
    assert store.sweep(IDLE, now=chat.last_active + IDLE) == [sid]
    assert server.status == "cancelled"  # type: ignore[attr-defined]
    assert chat.session.status == "abandoned"
    with pytest.raises(KeyError):
        store.get(sid)


def test_touching_a_chat_restarts_its_idle_clock() -> None:
    store, sid, _ = store_with_a_draft()
    chat = store.get(sid)
    chat.last_active -= IDLE  # it has been idle for a full timeout
    chat.touch()
    assert store.sweep(IDLE, now=time.monotonic()) == []
    assert store.get(sid) is chat


def test_a_chat_in_the_middle_of_a_reply_is_left_alone() -> None:
    store, sid, server = store_with_a_draft()
    chat = store.get(sid)
    with chat.lock:  # a reply is being written
        assert store.sweep(IDLE, now=chat.last_active + IDLE * 2) == []
    assert chat.session.status == "open" and server.status == "draft"  # type: ignore[attr-defined]
    assert store.sweep(IDLE, now=chat.last_active + IDLE * 2) == [sid]  # the next sweep ends it


def test_a_placed_order_is_forgotten_but_not_cancelled() -> None:
    session, _, server = make_session(
        [
            plan(TIKKI), say("Added."),
            plan({"type": "read_back"}), say("Shall I place it?"),
            plan({"type": "place_order"}), say("Placed."),
        ]
    )  # fmt: skip
    for text in ("one tikki", "that's all", "yes"):
        session.send(text)
    store = SessionStore()
    sid = store.add(session)
    assert store.sweep(IDLE, now=store.get(sid).last_active + IDLE) == [sid]
    assert server.status == "confirmed"
    assert session.status == "placed"
