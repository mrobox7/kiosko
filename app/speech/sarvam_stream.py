"""Streaming text-to-speech over Sarvam's WebSocket. The only file importing the Sarvam SDK.

Sentences go in as they are written and audio comes out as it is made. Each sentence is flushed
on its own, so the server speaks it at once instead of waiting to fill its buffer."""

import asyncio
import base64
import binascii
import logging
from collections.abc import AsyncIterator
from typing import Any

from sarvamai import AsyncSarvamAI, AudioOutput
from sarvamai.core.api_error import ApiError
from sarvamai.types.error_response import ErrorResponse
from sarvamai.types.event_response import EventResponse
from websockets.exceptions import WebSocketException

from app.speech.contract import Audio, SpeechError
from app.speech.sarvam import DEFAULT_TTS_LANGUAGE, TTS_MAX_CHARS

logger = logging.getLogger(__name__)

POLL_S = 0.25  # how often the receive loop looks at the sender while no audio arrives


async def _send(ws: Any, sentences: AsyncIterator[str]) -> int:
    """Send and flush each sentence as it arrives. Returns how many were flushed."""
    flushed = 0
    async for sentence in sentences:
        text = sentence.strip()
        if not text:
            continue
        if len(text) > TTS_MAX_CHARS:
            raise SpeechError(f"Sentence is {len(text)} characters; the limit is {TTS_MAX_CHARS}")
        await ws.convert(text)
        await ws.flush()
        flushed += 1
    return flushed


def _clip(message: AudioOutput) -> Audio:
    try:
        data = base64.b64decode(message.data.audio, validate=True)
    except binascii.Error as exc:
        raise SpeechError("Sarvam audio is not valid base64") from exc
    return Audio(data=data, mime_type=message.data.content_type)


class SarvamStreamingTextToSpeech:
    """StreamingTextToSpeech over one WebSocket per call to `stream`. The SDK's streaming
    settings have no `temperature`, unlike the REST adapter."""

    def __init__(
        self,
        client: AsyncSarvamAI,
        *,
        model: str = "bulbul:v3",
        speaker: str = "shubh",
        pace: float = 1.0,
        codec: str = "mp3",
        sample_rate: int = 22050,
        idle_timeout_s: float = 5.0,
    ) -> None:
        self._client = client
        self._model = model
        self._speaker = speaker
        self._pace = pace
        self._codec = codec
        self._sample_rate = sample_rate
        self._idle_timeout_s = idle_timeout_s

    async def stream(
        self, sentences: AsyncIterator[str], *, language: str | None = None
    ) -> AsyncIterator[Audio]:
        """Speak the sentences and yield audio. Ends when the server has confirmed every flushed
        sentence, or after `idle_timeout_s` of silence once all sentences were sent."""
        try:
            async with self._client.text_to_speech_streaming.connect(
                model=self._model,
                send_completion_event="true",
            ) as ws:
                await ws.configure(
                    target_language_code=language or DEFAULT_TTS_LANGUAGE,
                    speaker=self._speaker,
                    pace=self._pace,
                    speech_sample_rate=self._sample_rate,
                    output_audio_codec=self._codec,
                )
                sender = asyncio.create_task(_send(ws, sentences))
                finals = 0
                idle = 0.0
                try:
                    while True:
                        if sender.done():
                            flushed = sender.result()  # raises what the sender raised
                            if finals >= flushed or idle >= self._idle_timeout_s:
                                if finals < flushed:
                                    logger.warning(
                                        "Sarvam TTS ended with %d of %d sentences confirmed",
                                        finals,
                                        flushed,
                                    )
                                return
                        try:
                            message = await asyncio.wait_for(ws.recv(), POLL_S)
                        except TimeoutError:
                            idle += POLL_S if sender.done() else 0.0
                            continue
                        idle = 0.0
                        if isinstance(message, AudioOutput):
                            yield _clip(message)
                        elif isinstance(message, ErrorResponse):
                            raise SpeechError(f"Sarvam streaming error: {message.data.message}")
                        elif isinstance(message, EventResponse):
                            finals += 1
                finally:
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
        except ApiError as exc:
            status = exc.status_code or 0
            raise SpeechError(
                f"Sarvam streaming failed ({status})", retryable=status == 429 or status >= 500
            ) from exc
        except (WebSocketException, OSError) as exc:
            raise SpeechError(f"Sarvam streaming connection failed: {exc}", retryable=True) from exc
