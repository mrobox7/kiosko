"""The voice socket through FastAPI's test client, with fake speech services and a fake model."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.app import create_app
from app.api.voice import BUSY, NOT_HEARD, SILENCE
from app.domain.messages import ToolCall
from app.llm.base import LLMResponse
from app.llm.fake import FakeLLM
from app.session.factory import Runtime
from app.session.session import Session
from app.speech.base import SpeechError, Transcript
from app.speech.fake import FAKE_MIME, FakeSpeechToText, FakeStreamingTextToSpeech
from tests.support.builders import chat_texts, clock, make_loop
from tests.support.fake_backend import FakeBackend

SLOT = "2030-06-10T19:30:00"
PRIYA = {"phone": "+91-9876543210"}
HEARD = Transcript(text="book a table", language="en-IN")


class Rig:
    """A client, a logged-in session and the fakes behind it."""

    def __init__(
        self,
        llm_steps: list[LLMResponse],
        heard: list[Transcript | Exception],
        tts: FakeStreamingTextToSpeech | None = None,
    ) -> None:
        self.stt = FakeSpeechToText(heard)
        self.tts = tts or FakeStreamingTextToSpeech()
        runtime = Runtime(
            backend=FakeBackend().client,
            loop=make_loop(FakeLLM(llm_steps)),
            clock=clock,
            stt=self.stt,
            tts_stream=self.tts,
        )
        self.client = TestClient(create_app(runtime))
        self.sid = self.client.post("/api/login", json=PRIYA).json()["session_id"]

    @property
    def url(self) -> str:
        return f"/api/sessions/{self.sid}/voice"

    @property
    def session(self) -> Session:
        return self.client.app.state.store.get(self.sid).session


def without_voice() -> TestClient:
    runtime = Runtime(backend=FakeBackend().client, loop=make_loop(FakeLLM([])), clock=clock)
    return TestClient(create_app(runtime))


def until_reply(ws: Any) -> list[dict[str, Any]]:
    """Every JSON event up to and including the reply (audio chunks are skipped)."""
    events: list[dict[str, Any]] = []
    while not events or events[-1]["type"] not in ("reply", "error"):
        message = ws.receive()
        if message.get("text"):
            events.append(json.loads(message["text"]))
    return events


def test_one_utterance_streams_what_was_heard_the_audio_and_the_reply() -> None:
    rig = Rig([LLMResponse(text="Booked. See you then!")], [HEARD])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"RIFF-clip")
        assert ws.receive_json() == {"type": "heard", "text": "book a table", "language": "en-IN"}
        assert ws.receive_json() == {"type": "audio_start", "mime": FAKE_MIME}
        assert [ws.receive_bytes(), ws.receive_bytes()] == [b"Booked.", b"See you then!"]
        done = ws.receive_json()
    assert done["type"] == "reply" and done["text"] == "Booked. See you then!"
    assert done["stop_reason"] == "answered" and done["speech_error"] is None
    assert isinstance(done["first_audio_ms"], int) and done["trace"][0]["event"] == "GuardDecided"
    assert chat_texts(rig.session.history) == [
        ("user", "book a table"),
        ("assistant", "Booked. See you then!"),
    ]


def test_the_clip_goes_to_speech_to_text_as_wav_and_the_language_to_the_voice() -> None:
    rig = Rig([LLMResponse(text="Hi.")], [Transcript(text="namaste", language="hi-IN")])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"clip-bytes")
        until_reply(ws)
    assert [(c.audio.data, c.audio.mime_type) for c in rig.stt.calls] == [
        (b"clip-bytes", "audio/wav")
    ]
    assert rig.tts.language == "hi-IN" and rig.tts.spoken == ["Hi."]


def test_a_voice_turn_can_book_and_the_booking_shows_in_the_session() -> None:
    book = LLMResponse(
        tool_calls=[
            ToolCall(
                id="c",
                name="create_reservation",
                arguments={"slot_datetime": SLOT, "party_size": 4, "location": "outdoor"},
            )
        ]
    )
    rig = Rig([book, LLMResponse(text="Booked for four.")], [HEARD])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"clip")
        events = until_reply(ws)
    assert events[-1]["text"] == "Booked for four."
    upcoming = rig.client.get(f"/api/sessions/{rig.sid}").json()["upcoming"]
    assert [(b["party_size"], b["slot_datetime"]) for b in upcoming] == [(4, SLOT)]


def test_a_clip_that_cannot_be_transcribed_is_reported_and_the_socket_stays_open() -> None:
    rig = Rig([LLMResponse(text="Hello.")], [SpeechError("bad audio"), HEARD])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"noise")
        assert ws.receive_json() == {"type": "error", "message": NOT_HEARD}
        ws.send_bytes(b"clear speech")
        assert ws.receive_json()["type"] == "heard"


def test_an_empty_transcript_is_reported_as_silence() -> None:
    rig = Rig([], [Transcript(text="", language=None)])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"quiet")
        assert ws.receive_json() == {"type": "error", "message": SILENCE}


def test_text_frames_are_ignored() -> None:
    rig = Rig([LLMResponse(text="Hi.")], [HEARD])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_text("hello?")
        ws.send_bytes(b"clip")
        assert ws.receive_json()["type"] == "heard"


def test_an_utterance_while_a_reply_is_being_written_is_turned_away() -> None:
    rig = Rig([], [HEARD])
    lock = rig.client.app.state.store.get(rig.sid).lock
    lock.acquire()
    try:
        with rig.client.websocket_connect(rig.url) as ws:
            ws.send_bytes(b"clip")
            assert ws.receive_json() == {"type": "error", "message": BUSY}
    finally:
        lock.release()


def test_a_speech_failure_still_delivers_the_reply_text() -> None:
    rig = Rig(
        [LLMResponse(text="Done.")],
        [HEARD],
        FakeStreamingTextToSpeech(error=SpeechError("tts down")),
    )
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"clip")
        events = until_reply(ws)
    assert [e["type"] for e in events] == ["heard", "reply"]
    assert events[-1]["text"] == "Done." and events[-1]["speech_error"] == "tts down"


def test_login_says_whether_the_page_can_offer_the_microphone() -> None:
    assert without_voice().post("/api/login", json=PRIYA).json()["voice"] is False
    assert Rig([], []).client.post("/api/login", json=PRIYA).json()["voice"] is True


def test_the_socket_is_refused_when_voice_is_not_set_up_or_the_session_is_unknown() -> None:
    plain = without_voice()
    sid = plain.post("/api/login", json=PRIYA).json()["session_id"]
    with (
        pytest.raises(WebSocketDisconnect) as no_voice,
        plain.websocket_connect(f"/api/sessions/{sid}/voice"),
    ):
        pass
    assert no_voice.value.code == 4403
    rig = Rig([], [])
    with (
        pytest.raises(WebSocketDisconnect) as unknown,
        rig.client.websocket_connect("/api/sessions/nope/voice"),
    ):
        pass
    assert unknown.value.code == 4404


HEARD_AGAIN = Transcript(text="make it eight", language="en-IN")


def test_an_interrupt_cuts_the_speech_off_and_the_reply_text_still_arrives() -> None:
    rig = Rig(
        [LLMResponse(text="One. Two. Three.")],
        [HEARD],
        FakeStreamingTextToSpeech(hang_after=1),  # a slow voice: stalls after the first sentence
    )
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"clip")
        assert ws.receive_json()["type"] == "heard"
        assert ws.receive_json()["type"] == "audio_start"
        assert ws.receive_bytes() == b"One."
        ws.send_json({"type": "interrupt"})
        done = until_reply(ws)[-1]
    assert done["type"] == "reply" and done["interrupted"] is True
    assert done["text"] == "One. Two. Three."  # the turn itself finished and is shown
    assert rig.tts.closed
    assert chat_texts(rig.session.history)[-1] == ("assistant", "One. Two. Three.")


def next_event(ws: Any) -> dict[str, Any]:
    """The next JSON event, skipping audio chunks."""
    while True:
        message = ws.receive()
        if message.get("text"):
            return json.loads(message["text"])


def test_a_clip_sent_right_after_an_interrupt_waits_for_the_cut_off_turn_instead_of_failing() -> (
    None
):
    rig = Rig(
        [LLMResponse(text="One. Two."), LLMResponse(text="Eight it is.")],
        [HEARD, HEARD_AGAIN],
        FakeStreamingTextToSpeech(hang_after=1),
    )
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_bytes(b"first")
        assert next_event(ws)["type"] == "heard"
        assert next_event(ws)["type"] == "audio_start"
        ws.receive_bytes()  # the first sentence
        ws.send_json({"type": "interrupt"})
        ws.send_bytes(b"second")  # the customer talks over it straight away
        first_turn = next_event(ws)
        second_turn = next_event(ws)
        ws.send_json({"type": "interrupt"})  # end the second turn too, so nothing is left running
        assert next_event(ws)["type"] == "reply"
    assert first_turn["type"] == "reply" and first_turn["interrupted"] is True
    assert second_turn == {"type": "heard", "text": "make it eight", "language": "en-IN"}


def test_an_interrupt_when_nothing_is_running_is_ignored() -> None:
    rig = Rig([LLMResponse(text="Hi.")], [HEARD])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_json({"type": "interrupt"})
        ws.send_text("not json at all")
        ws.send_bytes(b"clip")
        events = until_reply(ws)
    assert events[-1]["type"] == "reply" and events[-1]["interrupted"] is False


def test_an_interrupt_does_not_carry_over_to_the_next_turn() -> None:
    rig = Rig([LLMResponse(text="Hi.")], [HEARD])
    with rig.client.websocket_connect(rig.url) as ws:
        ws.send_json({"type": "interrupt"})  # nothing to interrupt yet
        ws.send_bytes(b"clip")
        events = until_reply(ws)
    assert events[-1]["interrupted"] is False and rig.tts.spoken == ["Hi."]
