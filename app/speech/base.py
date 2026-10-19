"""The speech contracts: audio and transcript types, client protocols, error."""

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

__all__ = [
    "Audio",
    "SpeechError",
    "SpeechToText",
    "StreamingTextToSpeech",
    "TextToSpeech",
    "Transcript",
]


class Audio(BaseModel, frozen=True):
    """One clip: encoded bytes and their MIME type, e.g. `audio/wav`."""

    data: bytes
    mime_type: str


class Transcript(BaseModel, frozen=True):
    """What was heard. `language` is a BCP-47 tag such as `en-IN`, or None if unknown."""

    text: str
    language: str | None = None


class SpeechError(Exception):
    """Timeout, rate limit or provider error, after the adapter retried."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class SpeechToText(Protocol):
    """Anything that turns a clip into text. Raises only SpeechError."""

    def transcribe(self, audio: Audio, *, language: str | None = None) -> Transcript:
        """Transcribe the clip. `language` is a hint; None lets the provider detect it."""
        ...


class TextToSpeech(Protocol):
    """Anything that turns text into a clip. Raises only SpeechError."""

    def synthesize(self, text: str, *, language: str | None = None) -> Audio:
        """Speak the text. `language` picks the voice language; None uses the provider default."""
        ...


class StreamingTextToSpeech(Protocol):
    """Anything that speaks sentences as they arrive. Raises only SpeechError."""

    def stream(
        self, sentences: AsyncIterator[str], *, language: str | None = None
    ) -> AsyncIterator[Audio]:
        """Speak each sentence from `sentences` and yield audio chunks as they are produced,
        without waiting for the sentences to finish. The stream ends once everything is spoken.
        Closing the returned iterator stops the speech: that is how an interruption works."""
        ...
