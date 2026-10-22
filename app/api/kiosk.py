"""The kiosk screen's routes: the menu to browse and the taps on the cart. A tap runs the same
tool the model would, with no model call, so the order the chat sees is the order on the screen."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.schemas import LineIn, MenuOut, QuantityIn, SessionOut
from app.api.sessions import Chat
from app.domain.results import BACKEND_UNAVAILABLE
from app.session.factory import Runtime
from app.session.session import Session, SessionClosed


def kiosk_router(
    runtime: Runtime,
    chat_of: Callable[[str], Chat],
    view: Callable[[str, Session], SessionOut],
) -> APIRouter:
    """`chat_of` finds a chat by its id (404 if unknown); `view` describes its session."""
    router = APIRouter(prefix="/api")

    def act(session_id: str, tool: str, args: dict[str, Any]) -> SessionOut:
        chat = chat_of(session_id)
        if not chat.lock.acquire(blocking=False):
            raise HTTPException(409, "A reply is still being written")
        chat.touch()
        try:
            result = chat.session.act(tool, args)
        except SessionClosed as exc:
            raise HTTPException(409, f"This order is {exc}. Start a new one.") from exc
        finally:
            chat.touch()
            chat.lock.release()
        if not result.ok:
            error = result.error
            assert error is not None  # a failed result always carries its error
            status = 503 if error.code == BACKEND_UNAVAILABLE else 422
            raise HTTPException(status, error.model_dump())
        return view(session_id, chat.session)

    @router.get("/menu")
    def menu() -> MenuOut:
        return MenuOut(
            version=runtime.menu.version,
            outlet=runtime.outlet,
            categories=list(runtime.menu.categories),
            dishes=list(runtime.menu.dishes),
        )

    @router.post("/sessions/{session_id}/lines", status_code=201)
    def add_line(session_id: str, body: LineIn) -> SessionOut:
        args = body.model_dump(exclude_none=True)
        return act(session_id, "add_to_order", args)

    @router.patch("/sessions/{session_id}/lines/{line_id}")
    def change_line(session_id: str, line_id: int, body: QuantityIn) -> SessionOut:
        return act(session_id, "change_quantity", {"line_id": line_id, "quantity": body.quantity})

    @router.delete("/sessions/{session_id}/lines/{line_id}")
    def remove_line(session_id: str, line_id: int) -> SessionOut:
        return act(session_id, "remove_from_order", {"line_id": line_id})

    @router.post("/sessions/{session_id}/place")
    def place(session_id: str) -> SessionOut:
        return act(session_id, "place_order", {})

    return router
