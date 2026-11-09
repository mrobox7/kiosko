"""The FastAPI app. Routes are thin: the chat turn and the order live in `app.session`."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket

from app.agent.prompts import greeting
from app.api.kiosk import kiosk_router
from app.api.schemas import MessageIn, ReplyOut, SessionOut, session_out, trace_of
from app.api.voice import run_voice
from app.config import settings
from app.runtime import Runtime
from app.session.session import Session, SessionClosed
from app.session.store import Chat, SessionStore

logger = logging.getLogger(__name__)


async def end_idle_chats(store: SessionStore, idle_s: float) -> None:
    """Forever: every so often, end the chats nobody has touched for `idle_s` seconds."""
    every = max(1.0, min(30.0, idle_s / 4))
    while True:
        await asyncio.sleep(every)
        try:
            ended = await asyncio.to_thread(store.sweep, idle_s, time.monotonic())
        except Exception:
            logger.exception("Sweeping idle chats failed")
            continue
        if ended:
            logger.info("Ended %d idle chat(s)", len(ended))


def create_app(runtime: Runtime, idle_timeout_s: float | None = None) -> FastAPI:
    """Build the API around the shared runtime. Chats idle for `idle_timeout_s` seconds (default
    from the settings) are ended and their draft orders cancelled."""
    store = SessionStore()
    idle_s = settings.idle_timeout_s if idle_timeout_s is None else idle_timeout_s

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        sweeper = asyncio.create_task(end_idle_chats(store, idle_s))
        yield
        sweeper.cancel()

    app = FastAPI(title="DishPatch", lifespan=lifespan)
    stt, tts = runtime.stt, runtime.tts_stream
    voice = stt is not None and tts is not None
    app.state.store = store  # for tests and tooling

    def chat_of(session_id: str) -> Chat:
        try:
            return store.get(session_id)
        except KeyError:
            raise HTTPException(404, "Unknown session") from None

    def view(session_id: str, session: Session) -> SessionOut:
        return session_out(session_id, session, voice=voice, idle_timeout_s=idle_s)

    app.include_router(kiosk_router(runtime, chat_of, view))

    @app.post("/api/sessions", status_code=201)
    def start() -> SessionOut:
        """The next customer at the lane: a chat with one order and nobody identified yet."""
        session = runtime.start_session()
        return session_out(
            store.add(session),
            session,
            voice=voice,
            idle_timeout_s=idle_s,
            greeting=greeting(runtime.outlet.name),
        )

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> SessionOut:
        return view(session_id, chat_of(session_id).session)

    @app.post("/api/sessions/{session_id}/keepalive", status_code=204)
    def keep_alive(session_id: str) -> None:
        """The customer is browsing: tell the server so it does not end the order as idle."""
        chat_of(session_id).touch()

    @app.post("/api/sessions/{session_id}/messages")
    def send(session_id: str, body: MessageIn) -> ReplyOut:
        chat = chat_of(session_id)
        if not chat.lock.acquire(blocking=False):
            raise HTTPException(409, "A reply is still being written")
        chat.touch()
        try:
            reply = chat.session.send(body.text)
        except SessionClosed as exc:
            raise HTTPException(409, f"This order is {exc}. Start a new one.") from exc
        finally:
            chat.touch()
            chat.lock.release()
        return ReplyOut(
            text=reply.text, stop_reason=reply.stop_reason, trace=trace_of(reply.events)
        )

    @app.websocket("/api/sessions/{session_id}/voice")
    async def voice_socket(ws: WebSocket, session_id: str) -> None:
        if stt is None or tts is None:
            await ws.close(code=4403)  # voice is not set up
            return
        try:
            chat = store.get(session_id)
        except KeyError:
            await ws.close(code=4404)
            return
        await run_voice(ws, chat, stt, tts)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def end_session(session_id: str) -> None:
        """The customer left: cancel the draft, then forget the chat."""
        try:
            chat = store.get(session_id)
        except KeyError:
            return  # already gone: ending a session twice is harmless
        with chat.lock:
            chat.session.abandon()
        store.remove(session_id)

    return app
