import asyncio
from typing import Any

from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.speech.base import SpeechError
from app.speech.fake import FakeStreamingTextToSpeech
from app.speech.spoken_turn import speak_turn
from tests.support.builders import chat_texts, make_session


def run(coro: Any) -> Any:
    return asyncio.run(asyncio.wait_for(coro, 5))


def test_the_reply_is_spoken_sentence_by_sentence_and_timed() -> None:
    session, _, _ = make_session([LLMResponse(text="Booked for tonight. See you then!")])
    speaker = FakeStreamingTextToSpeech()
    result = run(speak_turn(session, "book me", speaker, language="en-IN"))
    assert [c.data for c in result.audio] == [b"Booked for tonight.", b"See you then!"]
    assert result.reply.text == "Booked for tonight. See you then!"
    assert result.first_audio_ms is not None and result.speech_error is None
    assert speaker.language == "en-IN" and not result.runaway


def test_on_a_tool_turn_only_the_final_answer_is_spoken() -> None:
    steps = [
        LLMResponse(tool_calls=[ToolCall(id="c", name="list_my_reservations", arguments={})]),
        LLMResponse(text="You have no bookings."),
    ]
    session, _, _ = make_session(steps)
    speaker = FakeStreamingTextToSpeech()
    run(speak_turn(session, "my bookings?", speaker))
    assert speaker.spoken == ["You have no bookings."]


def test_a_speech_failure_keeps_the_reply_and_the_turn() -> None:
    session, _, _ = make_session([LLMResponse(text="Done. Anything else?")])
    speaker = FakeStreamingTextToSpeech(error=SpeechError("tts down"), fail_after=1)
    result = run(speak_turn(session, "hi", speaker))
    assert result.speech_error == "tts down" and result.reply.text == "Done. Anything else?"
    assert chat_texts(session.history)[-1] == ("assistant", "Done. Anything else?")


def test_when_nothing_was_streamed_the_reply_text_is_spoken_instead() -> None:
    session, _, _ = make_session([], max_chars=10)
    speaker = FakeStreamingTextToSpeech()
    result = run(speak_turn(session, "x" * 11, speaker))  # refused by the guard, no model call
    assert result.reply.stop_reason == "refused"
    assert speaker.spoken == [result.reply.text] and result.first_audio_ms is not None


def test_a_runaway_reply_stops_the_voice_but_not_the_turn() -> None:
    garbage = "Fine.\n" + "...\n" * 8 + "More text.\n"
    session, _, _ = make_session([LLMResponse(text=garbage)])
    speaker = FakeStreamingTextToSpeech()
    result = run(speak_turn(session, "hi", speaker))
    assert speaker.spoken == ["Fine."] and result.runaway
    assert result.reply.stop_reason == "answered"


def test_each_clip_is_handed_to_the_listener_as_it_is_made() -> None:
    session, _, _ = make_session([LLMResponse(text="Booked. See you then!")])
    heard: list[bytes] = []

    async def listener(clip: Any) -> None:
        heard.append(clip.data)

    result = run(speak_turn(session, "hi", FakeStreamingTextToSpeech(), on_audio=listener))
    assert heard == [b"Booked.", b"See you then!"] == [c.data for c in result.audio]


def test_a_listener_that_fails_stops_the_forwarding_but_not_the_turn() -> None:
    session, _, _ = make_session([LLMResponse(text="One. Two. Three.")])
    calls: list[bytes] = []

    async def vanished(clip: Any) -> None:
        calls.append(clip.data)
        raise ConnectionResetError("tab closed")

    result = run(speak_turn(session, "hi", FakeStreamingTextToSpeech(), on_audio=vanished))
    assert calls == [b"One."]  # tried once, then gave up
    assert [c.data for c in result.audio] == [b"One.", b"Two.", b"Three."]
    assert result.reply.stop_reason == "answered"
    assert chat_texts(session.history)[-1] == ("assistant", "One. Two. Three.")


def test_a_stop_cuts_the_speech_off_but_the_turn_still_finishes_and_is_kept() -> None:
    session, _, _ = make_session([LLMResponse(text="One. Two. Three.")])
    speaker = FakeStreamingTextToSpeech(hang_after=1)  # a slow service: stalls after one clip
    stop = asyncio.Event()

    async def cut_after_the_first_clip(clip: Any) -> None:
        stop.set()

    result = run(speak_turn(session, "hi", speaker, on_audio=cut_after_the_first_clip, stop=stop))
    assert result.interrupted and [c.data for c in result.audio] == [b"One."]
    assert speaker.closed  # the speech connection was really closed
    assert result.reply.stop_reason == "answered"
    assert chat_texts(session.history)[-1] == ("assistant", "One. Two. Three.")


def test_a_stop_before_anything_is_spoken_also_keeps_the_turn_and_speaks_nothing_later() -> None:
    session, _, _ = make_session([LLMResponse(text="Fine.")])
    speaker = FakeStreamingTextToSpeech()
    stop = asyncio.Event()
    stop.set()
    result = run(speak_turn(session, "hi", speaker, stop=stop))
    assert result.interrupted and result.audio == [] and speaker.spoken == []
    assert chat_texts(session.history)[-1] == ("assistant", "Fine.")


def test_without_a_stop_nothing_is_interrupted() -> None:
    session, _, _ = make_session([LLMResponse(text="Fine.")])
    result = run(speak_turn(session, "hi", FakeStreamingTextToSpeech(), stop=asyncio.Event()))
    assert not result.interrupted and [c.data for c in result.audio] == [b"Fine."]
