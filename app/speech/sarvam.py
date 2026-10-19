"""Sarvam adapters for the speech contracts: speech-to-text (code-mix mode) and text-to-speech."""

import base64
import binascii
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.speech.base import Audio, SpeechError, Transcript

logger = logging.getLogger(__name__)

STT_PATH = "/speech-to-text"
TTS_PATH = "/text-to-speech"
TTS_MAX_CHARS = 2500  # Sarvam's limit for bulbul:v3
DEFAULT_TTS_LANGUAGE = "en-IN"  # the API requires one; speech-to-text can auto-detect


def sarvam_http(base_url: str, api_key: str, timeout_s: float) -> httpx.Client:
    """The HTTP client both adapters share: base URL, auth header, timeout."""
    return httpx.Client(
        base_url=base_url, headers={"api-subscription-key": api_key}, timeout=timeout_s
    )


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _post(
    http: httpx.Client,
    path: str,
    *,
    retries: int,
    sleep: Callable[[float], None],
    **request: Any,
) -> dict[str, Any]:
    """POST and return the JSON body. Retries 429, 5xx and network errors; raises SpeechError."""
    for attempt in range(retries + 1):
        try:
            response = http.post(path, **request)
        except httpx.TransportError as exc:  # includes timeouts
            error = SpeechError(f"Sarvam unreachable: {type(exc).__name__}", retryable=True)
        else:
            if response.is_success:
                return _json_object(response)
            error = SpeechError(
                f"Sarvam returned {response.status_code}: {_message(response)}",
                retryable=_retryable(response.status_code),
            )
        if not error.retryable or attempt == retries:
            raise error
        logger.warning("Sarvam call failed (%s), retrying", error)
        sleep(0.5 * 2**attempt)
    raise AssertionError("unreachable")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise SpeechError("Sarvam returned a body that is not JSON") from exc
    if not isinstance(body, dict):
        raise SpeechError("Sarvam returned an unexpected body")
    return body


def _message(response: httpx.Response) -> str:
    """The provider's own error message, never the request (it may carry the user's words)."""
    try:
        error = response.json().get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    except ValueError, AttributeError:
        pass
    return response.reason_phrase


class SarvamSpeechToText:
    """SpeechToText over Sarvam's REST API. Code-mix mode writes English words in Latin script
    and Indic words in native script, which suits Hinglish."""

    def __init__(
        self,
        http: httpx.Client,
        *,
        model: str = "saaras:v3",
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http
        self._model = model
        self._retries = retries
        self._sleep = sleep

    def transcribe(self, audio: Audio, *, language: str | None = None) -> Transcript:
        """Send the clip; `language=None` asks Sarvam to detect it."""
        body = _post(
            self._http,
            STT_PATH,
            retries=self._retries,
            sleep=self._sleep,
            data={"model": self._model, "mode": "codemix", "language_code": language or "unknown"},
            files={"file": ("clip", audio.data, audio.mime_type)},
        )
        text = body.get("transcript")
        if not isinstance(text, str):
            raise SpeechError("Sarvam reply has no transcript")
        detected = body.get("language_code")
        return Transcript(
            text=text.strip(), language=detected if isinstance(detected, str) else None
        )


class SarvamTextToSpeech:
    """TextToSpeech over Sarvam's REST API. Returns WAV."""

    def __init__(
        self,
        http: httpx.Client,
        *,
        model: str = "bulbul:v3",
        speaker: str = "shubh",
        pace: float = 1.0,
        temperature: float = 0.6,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http
        self._model = model
        self._speaker = speaker
        self._pace = pace
        self._temperature = temperature
        self._retries = retries
        self._sleep = sleep

    def synthesize(self, text: str, *, language: str | None = None) -> Audio:
        """Speak the text in one request; it must fit Sarvam's length limit."""
        if len(text) > TTS_MAX_CHARS:
            raise SpeechError(f"Text is {len(text)} characters; the limit is {TTS_MAX_CHARS}")
        body = _post(
            self._http,
            TTS_PATH,
            retries=self._retries,
            sleep=self._sleep,
            json={
                "text": text,
                "language_code": language or DEFAULT_TTS_LANGUAGE,
                "model": self._model,
                "speaker": self._speaker,
                "pace": self._pace,
                "temperature": self._temperature,
                "output_audio_codec": "wav",
            },
        )
        clips = body.get("audios")
        if not isinstance(clips, list) or not clips or not isinstance(clips[0], str):
            raise SpeechError("Sarvam reply has no audio")
        try:
            return Audio(data=base64.b64decode(clips[0], validate=True), mime_type="audio/wav")
        except binascii.Error as exc:
            raise SpeechError("Sarvam audio is not valid base64") from exc
