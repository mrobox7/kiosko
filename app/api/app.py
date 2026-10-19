"""The FastAPI app. Routes are thin: identification, the chat turn and the profile all live in
`app.session`."""

from fastapi import FastAPI, HTTPException, WebSocket

from app.api.schemas import LoginIn, MessageIn, ReplyOut, SessionOut, session_out, trace_of
from app.api.sessions import Chat, SessionStore
from app.api.voice import run_voice
from app.session.factory import Runtime
from app.session.identification import IdentificationError
from app.session.prompts import greeting


def create_app(runtime: Runtime) -> FastAPI:
    """Build the API around the shared runtime."""
    app = FastAPI(title="DishPatch")
    store = SessionStore()
    stt, tts = runtime.stt, runtime.tts_stream
    voice = stt is not None and tts is not None
    app.state.store = store  # for tests and tooling

    def chat_of(session_id: str) -> Chat:
        try:
            return store.get(session_id)
        except KeyError:
            raise HTTPException(404, "Unknown session") from None

    @app.post("/api/login")
    def login(body: LoginIn) -> SessionOut:
        try:
            session = runtime.login(name=body.name, phone=body.phone, email=body.email)
        except IdentificationError as exc:
            raise HTTPException(422, str(exc)) from exc
        return session_out(
            store.add(session), session, voice=voice, greeting=greeting(session.customer.name)
        )

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> SessionOut:
        return session_out(session_id, chat_of(session_id).session, voice=voice)

    @app.post("/api/sessions/{session_id}/messages")
    def send(session_id: str, body: MessageIn) -> ReplyOut:
        chat = chat_of(session_id)
        if not chat.lock.acquire(blocking=False):
            raise HTTPException(409, "A reply is still being written")
        try:
            reply = chat.session.send(body.text)
        finally:
            chat.lock.release()
        return ReplyOut(
            text=reply.text, stop_reason=reply.stop_reason, trace=trace_of(reply.events)
        )

    @app.post("/api/sessions/{session_id}/new")
    def new_chat(session_id: str) -> SessionOut:
        chat = chat_of(session_id)
        if not chat.lock.acquire(blocking=False):
            raise HTTPException(409, "A reply is still being written")
        try:
            chat.session = runtime.start_session(chat.session.customer)
        finally:
            chat.lock.release()
        return session_out(
            session_id,
            chat.session,
            voice=voice,
            greeting=greeting(chat.session.customer.name),
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
        store.remove(session_id)

    return app
