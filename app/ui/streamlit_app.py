"""Minimal chat page: input box, reply, trace expander."""

import dataclasses

import streamlit as st

from app.config import settings
from app.session.factory import build_session
from app.session.session import Session

st.set_page_config(page_title="DishPatch", page_icon="🍽️")
st.title("DishPatch")


@st.cache_resource
def get_session() -> Session:
    """One Session per server process (stage 1 is stateless)."""
    return build_session()


try:
    session = get_session()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if "transcript" not in st.session_state:
    st.session_state.transcript = []

for entry in st.session_state.transcript:
    with st.chat_message(entry["role"]):
        st.write(entry["text"])
        if entry.get("trace"):
            with st.expander("Trace"):
                st.json(entry["trace"])

if prompt := st.chat_input("Ask about our menu"):
    if len(prompt) > settings.max_message_chars:
        st.warning(f"Please keep messages under {settings.max_message_chars} characters.")
        st.stop()
    st.session_state.transcript.append({"role": "user", "text": prompt})
    with st.spinner("Thinking..."):
        reply = session.send(prompt)
    trace = [{"event": type(e).__name__, **dataclasses.asdict(e)} for e in reply.events]
    st.session_state.transcript.append({"role": "assistant", "text": reply.text, "trace": trace})
    st.rerun()
