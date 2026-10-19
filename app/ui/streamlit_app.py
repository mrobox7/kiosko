"""Chat page: identification form, then chat with a trace expander."""

import asyncio
import dataclasses
from typing import Any

import streamlit as st

from app.session.factory import Runtime, build_runtime
from app.session.identification import IdentificationError
from app.session.prompts import greeting
from app.session.session import Session
from app.speech.base import Audio, SpeechError
from app.speech.spoken_turn import speak_turn

st.set_page_config(page_title="DishPatch", page_icon="🍽️")
st.title("DishPatch")


@st.cache_resource
def get_runtime() -> Runtime:
    """Shared dependencies, built once per server process."""
    return build_runtime()


try:
    runtime = get_runtime()
except ValueError as exc:
    st.error(str(exc))
    st.stop()


def start_chat(session: Session) -> None:
    st.session_state.session = session
    st.session_state.transcript = [{"role": "assistant", "text": greeting(session.customer.name)}]


session: Session | None = st.session_state.get("session")

if session is None:
    st.subheader("Welcome")
    with st.form("identify"):
        phone = st.text_input("Phone number")
        email = st.text_input("Email")
        name = st.text_input("Name (only if you are new)")
        submitted = st.form_submit_button("Start")
    if submitted:
        try:
            start_chat(runtime.login(name=name, phone=phone, email=email))
        except IdentificationError as exc:
            st.warning(str(exc))
        else:
            st.rerun()
    st.stop()

with st.sidebar:
    st.write(f"Signed in as **{session.customer.name}**")
    st.subheader("Remembered")
    if session.profile.memory_unavailable:
        st.warning("Saved preferences could not be loaded, so this chat starts without them.")
    elif facts := session.profile.facts():
        for label, value in facts:
            st.write(f"**{label}:** {value}")
    else:
        st.caption("Nothing saved yet.")
    if st.button("New chat"):
        start_chat(runtime.start_session(session.customer))
        st.rerun()

for i, entry in enumerate(st.session_state.transcript):
    with st.chat_message(entry["role"]):
        st.write(entry["text"])
        if entry.get("audio"):
            fresh = i == len(st.session_state.transcript) - 1 and st.session_state.pop(
                "autoplay", False
            )
            st.audio(entry["audio"], format=entry.get("audio_mime", "audio/wav"), autoplay=fresh)
        if entry.get("trace"):
            with st.expander("Trace"):
                st.json(entry["trace"])


def take_turn(
    session: Session, text: str, *, spoken: bool = False, language: str | None = None
) -> None:
    """Send one customer message. A spoken one is answered in text and in voice."""
    st.session_state.transcript.append({"role": "user", "text": text})
    if spoken and runtime.tts_stream:
        with st.spinner("Thinking..."):
            turn = asyncio.run(speak_turn(session, text, runtime.tts_stream, language=language))
        reply, audio = turn.reply, turn.audio
    else:
        with st.spinner("Thinking..."):
            reply, audio, turn = session.send(text, spoken=spoken), [], None
    trace = [{"event": type(e).__name__, **dataclasses.asdict(e)} for e in reply.events]
    entry: dict[str, Any] = {"role": "assistant", "text": reply.text, "trace": trace}
    if turn is not None:
        trace.append(
            {"event": "Spoken", "first_audio_ms": turn.first_audio_ms, "runaway": turn.runaway}
        )
        if audio:
            entry["audio"] = b"".join(clip.data for clip in audio)
            entry["audio_mime"] = audio[0].mime_type
            st.session_state.autoplay = True
        if turn.speech_error:
            st.toast("Voice reply unavailable; showing text only.")
    st.session_state.transcript.append(entry)
    st.rerun()


message = st.chat_input("How can we help?", accept_audio=runtime.stt is not None)
if message:
    recording = getattr(message, "audio", None)
    if recording is None:
        take_turn(session, message if isinstance(message, str) else message.text)
    else:
        try:
            with st.spinner("Listening..."):
                assert runtime.stt  # the mic only shows when speech-to-text is set up
                heard = runtime.stt.transcribe(
                    Audio(data=recording.getvalue(), mime_type="audio/wav")
                )
        except SpeechError:
            st.warning("I could not make out that recording. Please try again or type.")
        else:
            if heard.text:
                take_turn(session, heard.text, spoken=True, language=heard.language)
            else:
                st.warning("I did not hear anything. Please try again or type.")
