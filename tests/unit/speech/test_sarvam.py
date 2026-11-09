"""Sarvam adapters against a stubbed HTTP transport (documented request and reply shapes)."""

import base64
import json
from collections.abc import Callable

import httpx
import pytest

from app.speech.contract import Audio, SpeechError, SpeechToText, TextToSpeech
from app.speech.sarvam import SarvamSpeechToText, SarvamTextToSpeech, sarvam_http

CLIP = Audio(data=b"RIFFfake", mime_type="audio/wav")
Handler = Callable[[httpx.Request], httpx.Response]


def http(handler: Handler) -> httpx.Client:
    client = sarvam_http("https://sarvam.test", "KEY", 5)
    client._transport = httpx.MockTransport(handler)  # noqa: SLF001 - keep the real headers
    return client


def stt(handler: Handler, sleeps: list[float] | None = None) -> SpeechToText:
    s = [] if sleeps is None else sleeps
    return SarvamSpeechToText(http(handler), retries=2, sleep=s.append)


def tts(handler: Handler, sleeps: list[float] | None = None) -> TextToSpeech:
    s = [] if sleeps is None else sleeps
    return SarvamTextToSpeech(http(handler), retries=2, sleep=s.append)


def ok(body: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=body)


def test_stt_sends_codemix_request_and_parses_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok({"transcript": " mujhe kal ek table book karna hai ", "language_code": "hi-IN"})

    result = stt(handler).transcribe(CLIP)
    assert result.text == "mujhe kal ek table book karna hai" and result.language == "hi-IN"
    request = seen[0]
    assert request.url == "https://sarvam.test/speech-to-text"
    assert request.headers["api-subscription-key"] == "KEY"
    body = request.read()
    for part in (b'name="mode"\r\n\r\ncodemix', b"saaras:v3", b"\r\n\r\nunknown", b"RIFFfake"):
        assert part in body


def test_stt_passes_a_language_hint() -> None:
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.read())
        return ok({"transcript": "hello", "language_code": None})

    result = stt(handler).transcribe(CLIP, language="en-IN")
    assert b"\r\n\r\nen-IN" in seen[0] and result.language is None


def test_stt_rejects_a_reply_without_transcript() -> None:
    with pytest.raises(SpeechError):
        stt(lambda r: ok({"request_id": "x"})).transcribe(CLIP)


def test_retries_rate_limit_then_succeeds() -> None:
    replies = [
        httpx.Response(429, json={"error": {"message": "slow down"}}),
        ok({"transcript": "hi"}),
    ]
    sleeps: list[float] = []
    assert stt(lambda r: replies.pop(0), sleeps).transcribe(CLIP).text == "hi"
    assert sleeps == [0.5]


def test_gives_up_after_the_retries_and_marks_the_error_retryable() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(SpeechError) as caught:
        stt(handler).transcribe(CLIP)
    assert len(calls) == 3 and caught.value.retryable


def test_client_error_is_not_retried_and_does_not_leak_the_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(422, json={"error": {"message": "bad audio", "code": "x"}})

    with pytest.raises(SpeechError, match="422: bad audio") as caught:
        stt(handler).transcribe(CLIP)
    assert len(calls) == 1 and not caught.value.retryable
    assert "KEY" not in str(caught.value)


def test_network_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(SpeechError) as caught:
        stt(handler).transcribe(CLIP)
    assert caught.value.retryable


def test_tts_sends_json_and_decodes_the_wav() -> None:
    seen: list[httpx.Request] = []
    wav = b"RIFF....WAVEdata"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok({"request_id": "r", "audios": [base64.b64encode(wav).decode()]})

    clip = tts(handler).synthesize("Aapki table book ho gayi.", language="hi-IN")
    assert clip == Audio(data=wav, mime_type="audio/wav")
    sent = json.loads(seen[0].read())
    assert seen[0].url == "https://sarvam.test/text-to-speech"
    assert sent == {
        "text": "Aapki table book ho gayi.",
        "language_code": "hi-IN",
        "model": "bulbul:v3",
        "speaker": "shubh",
        "pace": 1.0,
        "temperature": 0.6,
        "output_audio_codec": "wav",
    }


def test_tts_defaults_to_english_india() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.read()))
        return ok({"audios": [base64.b64encode(b"x").decode()]})

    tts(handler).synthesize("Hello")
    assert seen[0]["language_code"] == "en-IN"


def test_tts_rejects_text_over_the_limit_without_calling_sarvam() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called")

    with pytest.raises(SpeechError, match="limit"):
        tts(handler).synthesize("x" * 2501)


@pytest.mark.parametrize("body", [{"audios": []}, {"audios": ["!!not base64!!"]}, {}])
def test_tts_rejects_a_reply_without_usable_audio(body: dict[str, object]) -> None:
    with pytest.raises(SpeechError):
        tts(lambda r: ok(body)).synthesize("Hello")
