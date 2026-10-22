"""Wires the real dependencies. The only place that reads the wall clock."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from openai import OpenAI
from sarvamai import AsyncSarvamAI

from app.agent.loop import AgentLoop
from app.backend.client import BackendClient
from app.backend.errors import BackendError
from app.backend.models import Outlet
from app.config import settings
from app.domain.state import Clock
from app.guards.rules import RulesGuard
from app.llm.openai_compat import OpenAICompatLLM
from app.menu.menu import Menu
from app.session.session import Session
from app.speech.base import SpeechToText, StreamingTextToSpeech, TextToSpeech
from app.speech.sarvam import SarvamSpeechToText, SarvamTextToSpeech, sarvam_http
from app.speech.sarvam_stream import SarvamStreamingTextToSpeech
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class Runtime:
    """Process-wide dependencies shared by every session."""

    backend: BackendClient
    loop: AgentLoop
    clock: Clock
    menu: Menu  # the outlet's whole menu, shared by every chat
    outlet: Outlet  # its name and address, for the greeting and the prompt
    stt: SpeechToText | None = None  # None when no Sarvam key is set: the UI hides the mic
    tts: TextToSpeech | None = None
    tts_stream: StreamingTextToSpeech | None = None  # speaks sentences as they are written

    def start_session(self) -> Session:
        """A fresh chat for the next customer at the lane: one order, nobody identified yet."""
        self.menu.refresh()  # picks up a menu change before this customer starts
        return Session(
            loop=self.loop,
            ctx=ToolContext(
                backend=self.backend,
                clock=self.clock,
                outlet_code=settings.outlet_code,
                menu=self.menu,
            ),
            guard=RulesGuard(
                max_chars=settings.max_message_chars,
                turns_per_min=settings.rate_limit_turns_per_min,
                token_budget=settings.session_token_budget,
            ),
            clock=self.clock,
            summary_turns=settings.summary_turns,
            menu_outline=self.menu.outline,
            outlet=self.outlet,
        )


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
    loop = AgentLoop(
        llm,
        ToolRegistry.discover(),
        max_iterations=settings.max_iterations,
        max_tool_calls=settings.max_tool_calls_per_turn,
        tool_result_max_chars=settings.tool_result_max_chars,
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
    return Runtime(
        backend=backend,
        loop=loop,
        clock=lambda: datetime.now(tz),
        stt=stt,
        tts=tts,
        tts_stream=tts_stream,
        menu=menu,
        outlet=outlet,
    )
