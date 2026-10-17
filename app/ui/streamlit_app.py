"""Chat page: identification form, then chat with a trace expander."""

import dataclasses

import streamlit as st

from app.session.factory import Runtime, build_runtime
from app.session.identification import IdentificationError
from app.session.session import Session

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
    st.session_state.transcript = []


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
    if st.button("New chat"):
        start_chat(runtime.start_session(session.customer))
        st.rerun()

for entry in st.session_state.transcript:
    with st.chat_message(entry["role"]):
        st.write(entry["text"])
        if entry.get("trace"):
            with st.expander("Trace"):
                st.json(entry["trace"])

if prompt := st.chat_input("How can we help?"):
    st.session_state.transcript.append({"role": "user", "text": prompt})
    with st.spinner("Thinking..."):
        reply = session.send(prompt)
    trace = [{"event": type(e).__name__, **dataclasses.asdict(e)} for e in reply.events]
    st.session_state.transcript.append({"role": "assistant", "text": reply.text, "trace": trace})
    st.rerun()
