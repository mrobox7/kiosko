"""Wires the real dependencies. The only place that reads the wall clock."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from openai import OpenAI
from sarvamai import AsyncSarvamAI

from app.agent.graph import Graph, build_graph, make_saver
from app.agent.services import Services
from app.backend.client import BackendClient
from app.backend.errors import BackendError
from app.backend.models import Outlet
from app.config import settings
from app.llm.openai_compat import OpenAICompatLLM
from app.menu.menu import Menu
from app.session.session import Session
from app.speech.contract import SpeechToText, StreamingTextToSpeech, TextToSpeech
from app.speech.sarvam import SarvamSpeechToText, SarvamTextToSpeech, sarvam_http
from app.speech.sarvam_stream import SarvamStreamingTextToSpeech


@dataclass(frozen=True)
class Runtime:
    """Process-wide dependencies shared by every session: the graph with its one saver, and what
    its nodes use."""

    services: Services
    graph: Graph
    saver: InMemorySaver
    stt: SpeechToText | None = None  # None when no Sarvam key is set: the UI hides the mic
    tts: TextToSpeech | None = None
    tts_stream: StreamingTextToSpeech | None = None  # speaks sentences as they are written

    @property
    def menu(self) -> Menu:
        """The outlet's whole menu, shared by every chat."""
        return self.services.menu

    @property
    def outlet(self) -> Outlet:
        """Its name and address, for the greeting and the prompts."""
        return self.services.outlet

    def start_session(self) -> Session:
        """A fresh chat for the next customer at the lane: one order, nobody identified yet."""
        self.menu.refresh()  # picks up a menu change before this customer starts
        return Session(self.graph, self.saver, self.services, uuid.uuid4().hex)


def build_runtime() -> Runtime:
    """Create the shared dependencies from the environment settings."""
    settings.require_llm()
    settings.require_outlet()
    tz = ZoneInfo(settings.restaurant_timezone)
    backend = BackendClient(
        httpx.Client(base_url=settings.backend_url, timeout=settings.backend_timeout_s)
    )
    menu = Menu(backend, settings.outlet_code)
    try:
        outlet = backend.get_outlet(settings.outlet_code)
        menu.refresh()  # a wrong OUTLET_CODE or a dead backend stops startup here
    except BackendError as exc:
        raise RuntimeError(
            f"Cannot load outlet {settings.outlet_code} from the backend: {exc}"
        ) from exc
    llm = OpenAICompatLLM(
        OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            timeout=settings.llm_timeout_s,
            max_retries=0,
        ),
        settings.llm_model,
        max_output_tokens=settings.llm_max_output_tokens,
    )
    services = Services(
        backend=backend,
        menu=menu,
        llm=llm,
        clock=lambda: datetime.now(tz),
        outlet=outlet,
        max_chars=settings.max_message_chars,
        turns_per_min=settings.rate_limit_turns_per_min,
        token_budget=settings.session_token_budget,
    )
    stt: SarvamSpeechToText | None = None
    tts: SarvamTextToSpeech | None = None
    tts_stream: SarvamStreamingTextToSpeech | None = None
    if key := settings.sarvam_api_key.get_secret_value():
        speech_http = sarvam_http(settings.sarvam_base_url, key, settings.sarvam_timeout_s)
        stt = SarvamSpeechToText(speech_http, model=settings.sarvam_stt_model)
        tts = SarvamTextToSpeech(
            speech_http,
            model=settings.sarvam_tts_model,
            speaker=settings.sarvam_tts_speaker,
            pace=settings.sarvam_tts_pace,
            temperature=settings.sarvam_tts_temperature,
        )
        tts_stream = SarvamStreamingTextToSpeech(
            AsyncSarvamAI(api_subscription_key=key),
            model=settings.sarvam_tts_model,
            speaker=settings.sarvam_tts_speaker,
            pace=settings.sarvam_tts_pace,
        )
    saver = make_saver()
    return Runtime(
        services=services,
        graph=build_graph(services, saver),
        saver=saver,
        stt=stt,
        tts=tts,
        tts_stream=tts_stream,
    )
