"""One spoken turn end to end: the model writes, sentences are spoken as they are finished.

This is the glue between `Session.send(on_text=...)`, the sentence splitter and streaming
text-to-speech. It knows nothing about the page or the phone line that plays the audio."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from app.session.session import Reply, Session
from app.speech.base import Audio, SpeechError, StreamingTextToSpeech
from app.speech.sentences import SentenceFeed

logger = logging.getLogger(__name__)

OnAudio = Callable[[Audio], Awaitable[None]]


@dataclass(frozen=True)
class SpokenTurn:
    """The reply, the audio made for it and how fast it started. `speech_error` is set when
    speaking failed; the reply and everything the turn did still stand."""

    reply: Reply
    audio: list[Audio]
    first_audio_ms: int | None
    speech_error: str | None = None
    runaway: bool = False
    interrupted: bool = False  # the listener cut the speech short; the turn itself still finished


async def _one(text: str) -> AsyncIterator[str]:
    yield text


async def speak_turn(
    session: Session,
    text: str,
    tts: StreamingTextToSpeech,
    *,
    language: str | None = None,
    on_audio: OnAudio | None = None,
    stop: asyncio.Event | None = None,
) -> SpokenTurn:
    """Answer one spoken message. The model runs in a worker thread; each finished sentence goes
    straight to `tts`. Each audio chunk is passed to `on_audio` as it arrives; if that fails
    (the listener went away) the chunks are still collected and the turn still completes.
    If nothing was streamed (a refused message, a failed turn), the reply text itself is
    spoken, so the customer always hears the answer.

    Setting `stop` cuts the speech off at once (the speech connection is closed). The model's
    turn cannot be cancelled mid-flight, so it still finishes, and is kept in the history."""
    started = time.perf_counter()
    feed = SentenceFeed(asyncio.get_running_loop())
    clips: list[Audio] = []
    first_ms: int | None = None
    forward = on_audio

    async def collect(sentences: AsyncIterator[str]) -> None:
        nonlocal first_ms, forward
        async for clip in tts.stream(sentences, language=language):
            if first_ms is None:
                first_ms = int((time.perf_counter() - started) * 1000)
            clips.append(clip)
            if forward is not None:
                try:
                    await forward(clip)
                except Exception:  # boundary: a vanished listener must not undo the turn
                    logger.warning("Audio listener failed; no longer forwarding", exc_info=True)
                    forward = None

    def run_turn() -> Reply:
        try:
            return session.send(text, spoken=True, on_text=feed.push)
        finally:
            feed.close()

    async def until_stopped(speak: Callable[[], Awaitable[None]]) -> bool:
        """Run the speaking; False if `stop` was already set, or fired first and cancelled it."""
        if stop is not None and stop.is_set():
            return False
        task = asyncio.ensure_future(speak())
        if stop is None:
            await task
            return True
        waiter = asyncio.ensure_future(stop.wait())
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        if task.done():
            task.result()  # re-raises a SpeechError
            return True
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return False

    turn = asyncio.create_task(asyncio.to_thread(run_turn))
    error: str | None = None
    interrupted = False
    try:
        interrupted = not await until_stopped(lambda: collect(feed))
    except SpeechError as exc:
        error = str(exc)
    reply = await turn  # the turn finishes whatever happened to the speech
    if not clips and error is None and not interrupted:
        try:
            interrupted = not await until_stopped(lambda: collect(_one(reply.text)))
        except SpeechError as exc:
            error = str(exc)
    return SpokenTurn(reply, clips, first_ms, error, runaway=feed.runaway, interrupted=interrupted)
