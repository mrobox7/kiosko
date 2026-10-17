"""Wires the real dependencies into a Session."""

import httpx
from openai import OpenAI

from app.agent.loop import AgentLoop
from app.backend.client import BackendClient
from app.config import settings
from app.llm.openai_compat import OpenAICompatLLM
from app.session.session import Session
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


def build_session() -> Session:
    """Create a Session from the environment settings."""
    settings.require_llm()
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
    return Session(loop, ToolContext(backend=backend))
