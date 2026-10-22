"""The voice socket: the browser sends a recorded clip, the server answers with what it heard,
the spoken reply as audio chunks while it is made, and finally the reply text with its trace.

From the browser:
  <binary frame>                one utterance, as a WAV clip
  {"type": "interrupt"}         stop speaking now (the customer started talking)
From the server (JSON text frames unless noted):
  {"type": "heard", "text", "language"}            what the clip said
  {"type": "audio_start", "mime"}                  audio follows
  <binary frame>                                   one audio chunk, in order
  {"type": "reply", "text", "stop_reason", "trace", "first_audio_ms", "speech_error",
   "runaway", "interrupted"}                       the turn is over
  {"type": "error", "message"}                     this clip could not be handled

An interrupt cuts the speech off, but the model's turn cannot be cancelled mid-flight: it
finishes quietly, its reply is kept, and the next clip waits for it."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.api.schemas import trace_of
from app.api.sessions import Chat
from app.speech.base import Audio, SpeechError, SpeechToText, StreamingTextToSpeech
from app.speech.spoken_turn import speak_turn

logger = logging.getLogger(__name__)

CLIP_MIME = "audio/wav"
NOT_HEARD = "I could not make out that recording. Please try again or type."
SILENCE = "I did not hear anything. Please try again or type."
BUSY = "A reply is still being written"


def _is_interrupt(text: str) -> bool:
    try:
        message = json.loads(text)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get("type") == "interrupt"


async def run_voice(
    ws: WebSocket, chat: Chat, stt: SpeechToText, tts: StreamingTextToSpeech
) -> None:
    """Serve one voice connection until the browser leaves. One utterance at a time, sharing the
    chat's lock with typed messages."""
    await ws.accept()
    current: asyncio.Task[None] | None = None
    stop = asyncio.Event()
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") is not None:
                if _is_interrupt(message["text"]):
                    stop.set()
                continue
            clip = message.get("bytes")
            if clip is None:
                continue
            if current is not None and not current.done():
                if not stop.is_set():
                    await ws.send_json({"type": "error", "message": BUSY})
                    continue
                await current  # it was interrupted: let it finish quietly, then take this clip
            stop = asyncio.Event()
            current = asyncio.create_task(_turn(ws, chat, stt, tts, clip, stop))
    finally:
        stop.set()  # nobody is listening any more
        if current is not None:
            await asyncio.gather(current, return_exceptions=True)


async def _turn(
    ws: WebSocket,
    chat: Chat,
    stt: SpeechToText,
    tts: StreamingTextToSpeech,
    clip: bytes,
    stop: asyncio.Event,
) -> None:
    if not chat.lock.acquire(blocking=False):
        await ws.send_json({"type": "error", "message": BUSY})
        return
    chat.touch()
    try:
        await _utterance(ws, chat, stt, tts, clip, stop)
    except WebSocketDisconnect, RuntimeError:
        return  # the browser left mid-turn; the turn itself already finished
    except Exception:
        logger.exception("Voice turn failed")
    finally:
        chat.touch()
        chat.lock.release()


async def _utterance(
    ws: WebSocket,
    chat: Chat,
    stt: SpeechToText,
    tts: StreamingTextToSpeech,
    clip: bytes,
    stop: asyncio.Event,
) -> None:
    try:
        heard = await asyncio.to_thread(stt.transcribe, Audio(data=clip, mime_type=CLIP_MIME))
    except SpeechError:
        await ws.send_json({"type": "error", "message": NOT_HEARD})
        return
    if not heard.text:
        await ws.send_json({"type": "error", "message": SILENCE})
        return
    await ws.send_json({"type": "heard", "text": heard.text, "language": heard.language})

    started = False

    async def forward(audio: Audio) -> None:
        nonlocal started
        if not started:
            await ws.send_json({"type": "audio_start", "mime": audio.mime_type})
            started = True
        await ws.send_bytes(audio.data)

    turn = await speak_turn(
        chat.session, heard.text, tts, language=heard.language, on_audio=forward, stop=stop
    )
    done: dict[str, Any] = {
        "type": "reply",
        "text": turn.reply.text,
        "stop_reason": turn.reply.stop_reason,
        "trace": trace_of(turn.reply.events),
        "first_audio_ms": turn.first_audio_ms,
        "speech_error": turn.speech_error,
        "runaway": turn.runaway,
        "interrupted": turn.interrupted,
    }
    await ws.send_json(done)
