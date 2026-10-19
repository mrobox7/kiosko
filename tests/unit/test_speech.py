"""Speech contracts: the fakes satisfy the protocols and behave as scripted."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.speech.base import Audio, SpeechError, SpeechToText, TextToSpeech, Transcript
from app.speech.fake import (
    FAKE_MIME,
    FakeSpeechToText,
    FakeStreamingTextToSpeech,
    FakeTextToSpeech,
)

CLIP = Audio(data=b"\x00\x01", mime_type="audio/wav")


def listen(stt: SpeechToText) -> Transcript:
    return stt.transcribe(CLIP, language="en-IN")


def speak(tts: TextToSpeech) -> Audio:
    return tts.synthesize("Table booked.", language="hi-IN")


def test_stt_replays_steps_in_order_and_records_calls() -> None:
    stt = FakeSpeechToText(
        [Transcript(text="book a table", language="en-IN"), Transcript(text="two")]
    )
    assert listen(stt).text == "book a table"
    assert stt.transcribe(CLIP).text == "two"
    assert [c.language for c in stt.calls] == ["en-IN", None]
    assert stt.calls[0].audio == CLIP


def test_stt_raises_a_scripted_error() -> None:
    stt = FakeSpeechToText([SpeechError("rate limited", retryable=True)])
    with pytest.raises(SpeechError) as caught:
        listen(stt)
    assert caught.value.retryable


def test_stt_fails_loudly_when_called_more_often_than_scripted() -> None:
    with pytest.raises(AssertionError):
        listen(FakeSpeechToText([]))


def test_tts_returns_the_text_as_audio_and_records_the_call() -> None:
    tts = FakeTextToSpeech()
    clip = speak(tts)
    assert clip == Audio(data=b"Table booked.", mime_type=FAKE_MIME)
    assert tts.calls[0].text == "Table booked." and tts.calls[0].language == "hi-IN"


def test_tts_raises_its_error_but_still_records_the_call() -> None:
    tts = FakeTextToSpeech(error=SpeechError("down"))
    with pytest.raises(SpeechError):
        speak(tts)
    assert len(tts.calls) == 1


def test_speech_error_is_not_retryable_by_default() -> None:
    assert SpeechError("boom").retryable is False


def _spoken(fake: FakeStreamingTextToSpeech, *sentences: str) -> list[bytes]:
    async def sentences_in() -> AsyncIterator[str]:
        for s in sentences:
            yield s

    async def go() -> list[bytes]:
        return [c.data async for c in fake.stream(sentences_in(), language="hi-IN")]

    return asyncio.run(go())


def test_fake_streaming_tts_yields_a_clip_per_sentence_and_records_them() -> None:
    fake = FakeStreamingTextToSpeech()
    assert _spoken(fake, "One.", "Two.") == [b"One.", b"Two."]
    assert fake.spoken == ["One.", "Two."] and fake.language == "hi-IN" and fake.closed


def test_fake_streaming_tts_can_fail_part_way() -> None:
    fake = FakeStreamingTextToSpeech(error=SpeechError("down"), fail_after=1)
    with pytest.raises(SpeechError):
        _spoken(fake, "One.", "Two.")
    assert fake.spoken == ["One."] and fake.closed
