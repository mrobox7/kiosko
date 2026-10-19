"""Speech doubles for offline tests."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from app.speech.base import Audio, Transcript

FAKE_MIME = "audio/x-fake"


@dataclass
class TranscribeCall:
    """What the speech-to-text client was asked."""

    audio: Audio
    language: str | None


@dataclass
class SynthesizeCall:
    """What the text-to-speech client was asked."""

    text: str
    language: str | None


class FakeSpeechToText:
    """Replays scripted transcripts or exceptions and records every call."""

    def __init__(self, steps: Sequence[Transcript | Exception]) -> None:
        self._steps = list(steps)
        self.calls: list[TranscribeCall] = []

    def transcribe(self, audio: Audio, *, language: str | None = None) -> Transcript:
        """Return the next scripted step; fail if called more often than scripted."""
        self.calls.append(TranscribeCall(audio, language))
        if not self._steps:
            raise AssertionError("FakeSpeechToText called more times than scripted")
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class FakeTextToSpeech:
    """Returns the text itself as the clip's bytes, so a test can read back what was spoken.
    With `error` set, every call raises it instead. Records every call."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[SynthesizeCall] = []

    def synthesize(self, text: str, *, language: str | None = None) -> Audio:
        """Record the call, then raise the configured error or return the fake clip."""
        self.calls.append(SynthesizeCall(text, language))
        if self._error is not None:
            raise self._error
        return Audio(data=text.encode(), mime_type=FAKE_MIME)


class FakeStreamingTextToSpeech:
    """Yields each sentence as one clip (its text as bytes) the moment it arrives. With `error`
    set, the stream raises it after `fail_after` clips. `closed` turns True when the stream
    ends for any reason, so a test can see that an interruption really stopped it."""

    def __init__(
        self, error: Exception | None = None, fail_after: int = 0, hang_after: int | None = None
    ) -> None:
        self._error = error
        self._fail_after = fail_after
        self._hang_after = hang_after  # after this many clips, stall as a slow service would
        self.spoken: list[str] = []
        self.language: str | None = None
        self.closed = False

    async def stream(
        self, sentences: AsyncIterator[str], *, language: str | None = None
    ) -> AsyncIterator[Audio]:
        """Record what was spoken and yield a clip per sentence."""
        self.language = language
        self.closed = False
        try:
            async for sentence in sentences:
                if self._error is not None and len(self.spoken) >= self._fail_after:
                    raise self._error
                if self._hang_after is not None and len(self.spoken) >= self._hang_after:
                    await asyncio.sleep(3600)
                self.spoken.append(sentence)
                yield Audio(data=sentence.encode(), mime_type=FAKE_MIME)
        finally:
            self.closed = True
