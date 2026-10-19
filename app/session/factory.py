"""Wires the real dependencies. The only place that reads the wall clock."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from openai import OpenAI
from sarvamai import AsyncSarvamAI

from app.agent.loop import AgentLoop
from app.backend.client import BackendClient
from app.backend.models import Customer
from app.config import settings
from app.domain.state import Clock
from app.guards.rules import RulesGuard
from app.llm.openai_compat import OpenAICompatLLM
from app.memory.service import MemoryService
from app.session.identification import identify
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
    stt: SpeechToText | None = None  # None when no Sarvam key is set: the UI hides the mic
    tts: TextToSpeech | None = None
    tts_stream: StreamingTextToSpeech | None = None  # speaks sentences as they are written

    def start_session(self, customer: Customer) -> Session:
        """A fresh chat for an identified customer."""
        return Session(
            customer=customer,
            loop=self.loop,
            ctx=ToolContext(backend=self.backend, customer_id=customer.id, clock=self.clock),
            guard=RulesGuard(
                max_chars=settings.max_message_chars,
                turns_per_min=settings.rate_limit_turns_per_min,
                token_budget=settings.session_token_budget,
            ),
            clock=self.clock,
            memory=MemoryService(self.backend),
            summary_turns=settings.summary_turns,
        )

    def login(self, *, name: str = "", phone: str = "", email: str = "") -> Session:
        """Identify the customer (look up or create) and start their chat."""
        return self.start_session(identify(self.backend, name=name, phone=phone, email=email))


def build_runtime() -> Runtime:
    """Create the shared dependencies from the environment settings."""
    settings.require_llm()
    tz = ZoneInfo(settings.restaurant_timezone)
    backend = BackendClient(
        httpx.Client(base_url=settings.backend_url, timeout=settings.backend_timeout_s)
    )
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
    )
