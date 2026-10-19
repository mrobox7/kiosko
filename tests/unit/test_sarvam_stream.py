"""SarvamStreamingTextToSpeech against a fake socket that behaves like the server: every flush
produces the audio of what was sent, then a `final` event."""

import asyncio
import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from typing import Any

import pytest
from sarvamai import AudioOutput
from sarvamai.core.api_error import ApiError
from sarvamai.types.audio_output_data import AudioOutputData
from sarvamai.types.error_response import ErrorResponse
from sarvamai.types.error_response_data import ErrorResponseData
from sarvamai.types.event_response import EventResponse
from sarvamai.types.event_response_data import EventResponseData
from websockets.exceptions import ConnectionClosedError

from app.speech.base import Audio, SpeechError
from app.speech.sarvam_stream import SarvamStreamingTextToSpeech


def audio_message(text: str, content_type: str = "audio/mpeg") -> AudioOutput:
    data = AudioOutputData(
        content_type=content_type, audio=base64.b64encode(text.encode()).decode()
    )
    return AudioOutput(type="audio", data=data)


FINAL = EventResponse(type="event", data=EventResponseData(event_type="final"))


class FakeSocket:
    def __init__(self, *, silent_after: int | None = None, error: str | None = None) -> None:
        self.events: asyncio.Queue[Any] = asyncio.Queue()
        self.configured: dict[str, Any] = {}
        self.sent: list[str] = []
        self.flushes = 0
        self._pending: list[str] = []
        self._silent_after = silent_after
        self._error = error

    async def configure(self, **kw: Any) -> None:
        self.configured = kw

    async def convert(self, text: str) -> None:
        self.sent.append(text)
        self._pending.append(text)

    async def flush(self) -> None:
        self.flushes += 1
        if self._error:
            await self.events.put(
                ErrorResponse(type="error", data=ErrorResponseData(message=self._error))
            )
            return
        for text in self._pending:
            await self.events.put(audio_message(text.upper()))
        self._pending = []
        if self._silent_after is None or self.flushes <= self._silent_after:
            await self.events.put(FINAL)

    async def recv(self) -> Any:
        return await self.events.get()


class FakeSDK:
    def __init__(self, socket: FakeSocket | None = None, fail: Exception | None = None) -> None:
        self.socket = socket or FakeSocket()
        self.connect_kwargs: dict[str, Any] = {}
        self.exited = False
        self._fail = fail
        self.text_to_speech_streaming = NS(connect=self._connect)

    @asynccontextmanager
    async def _connect(self, **kw: Any) -> AsyncIterator[FakeSocket]:
        self.connect_kwargs = kw
        if self._fail:
            raise self._fail
        try:
            yield self.socket
        finally:
            self.exited = True


async def source(*sentences: str) -> AsyncIterator[str]:
    for s in sentences:
        yield s


def tts(sdk: FakeSDK, **kw: Any) -> SarvamStreamingTextToSpeech:
    return SarvamStreamingTextToSpeech(sdk, **kw)  # type: ignore[arg-type]


async def collect(stream: AsyncIterator[Audio]) -> list[Audio]:
    return [clip async for clip in stream]


def run(coro: Any) -> Any:
    return asyncio.run(asyncio.wait_for(coro, 5))


def test_sentences_become_audio_in_order_with_the_servers_content_type() -> None:
    sdk = FakeSDK()
    clips = run(collect(tts(sdk).stream(source("Hello there.", "How are you?"))))
    assert [c.data for c in clips] == [b"HELLO THERE.", b"HOW ARE YOU?"]
    assert {c.mime_type for c in clips} == {"audio/mpeg"}


def test_connects_and_configures_with_the_models_voice_settings() -> None:
    sdk = FakeSDK()
    adapter = tts(
        sdk, model="bulbul:v3", speaker="shubh", pace=1.1, codec="mulaw", sample_rate=8000
    )
    run(collect(adapter.stream(source("Namaste."), language="hi-IN")))
    assert sdk.connect_kwargs == {"model": "bulbul:v3", "send_completion_event": "true"}
    assert sdk.socket.configured == {
        "target_language_code": "hi-IN",
        "speaker": "shubh",
        "pace": 1.1,
        "speech_sample_rate": 8000,
        "output_audio_codec": "mulaw",
    }


def test_language_defaults_when_none_is_given() -> None:
    sdk = FakeSDK()
    run(collect(tts(sdk).stream(source("Hi."))))
    assert sdk.socket.configured["target_language_code"] == "en-IN"


def test_each_sentence_is_flushed_on_its_own_so_it_is_spoken_at_once() -> None:
    sdk = FakeSDK()
    run(collect(tts(sdk).stream(source("One.", "Two.", "Three."))))
    assert sdk.socket.sent == ["One.", "Two.", "Three."] and sdk.socket.flushes == 3


def test_blank_sentences_are_skipped() -> None:
    sdk = FakeSDK()
    run(collect(tts(sdk).stream(source("", "  ", "Real."))))
    assert sdk.socket.sent == ["Real."] and sdk.socket.flushes == 1


def test_no_sentences_means_no_audio_and_no_wait() -> None:
    sdk = FakeSDK()
    assert run(collect(tts(sdk, idle_timeout_s=60).stream(source()))) == []


def test_ends_when_every_flush_is_confirmed_not_after_the_idle_timeout() -> None:
    sdk = FakeSDK()
    # a 60 s idle timeout would fail the 5 s guard in run() if the stream waited for it
    assert len(run(collect(tts(sdk, idle_timeout_s=60).stream(source("A.", "B."))))) == 2


def test_ends_after_the_idle_timeout_if_a_confirmation_never_comes() -> None:
    sdk = FakeSDK(FakeSocket(silent_after=1))
    clips = run(collect(tts(sdk, idle_timeout_s=0.5).stream(source("A.", "B."))))
    assert [c.data for c in clips] == [b"A.", b"B."]


def test_audio_starts_before_the_last_sentence_is_even_written() -> None:
    sdk = FakeSDK()
    heard_first = asyncio.Event()

    async def slow_source() -> AsyncIterator[str]:
        yield "First."
        await heard_first.wait()  # the second sentence exists only after audio 1 was heard
        yield "Second."

    async def consume() -> list[bytes]:
        out = []
        async for clip in tts(sdk).stream(slow_source()):
            out.append(clip.data)
            heard_first.set()
        return out

    assert run(consume()) == [b"FIRST.", b"SECOND."]


def test_server_error_message_becomes_a_speech_error() -> None:
    sdk = FakeSDK(FakeSocket(error="quota exceeded"))
    with pytest.raises(SpeechError, match="quota exceeded"):
        run(collect(tts(sdk).stream(source("Hi."))))


def test_a_sentence_over_the_limit_is_refused_and_nothing_is_sent() -> None:
    sdk = FakeSDK()
    with pytest.raises(SpeechError, match="limit"):
        run(collect(tts(sdk).stream(source("x" * 2501))))
    assert sdk.socket.sent == []


def test_invalid_audio_is_a_speech_error() -> None:
    sdk = FakeSDK()
    bad = AudioOutput(type="audio", data=AudioOutputData(content_type="audio/mpeg", audio="!!"))
    sdk.socket.events.put_nowait(bad)
    with pytest.raises(SpeechError, match="base64"):
        run(collect(tts(sdk).stream(source("Hi."))))


def test_closing_the_stream_early_closes_the_connection() -> None:
    sdk = FakeSDK()

    async def interrupted() -> bytes:
        stream = tts(sdk).stream(source("One.", "Two.", "Three."))
        first = await anext(stream)
        await stream.aclose()  # an interruption
        return first.data

    assert run(interrupted()) == b"ONE."
    assert sdk.exited


@pytest.mark.parametrize(
    ("failure", "retryable"),
    [
        (ApiError(status_code=401, body="bad key"), False),
        (ApiError(status_code=503, body="down"), True),
        (ConnectionResetError("reset"), True),
        (ConnectionClosedError(None, None), True),
    ],
)
def test_connection_failures_become_speech_errors(failure: Exception, retryable: bool) -> None:
    sdk = FakeSDK(fail=failure)
    with pytest.raises(SpeechError) as info:
        run(collect(tts(sdk).stream(source("Hi."))))
    assert info.value.retryable is retryable
