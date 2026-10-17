"""Stage 1 demo: vegetarian starters under 400, through Session, loop, registry and backend."""

from app.agent.events import ToolRequested
from app.agent.loop import AgentLoop
from app.domain.messages import ToolCall
from app.llm.base import LLMError, LLMResponse
from app.llm.fake import FakeLLM
from app.session.session import Session
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.support.fake_backend import FakeBackend


def session_for(steps) -> tuple[Session, FakeLLM]:
    llm = FakeLLM(steps)
    loop = AgentLoop(
        llm,
        ToolRegistry.discover(),
        max_iterations=8,
        max_tool_calls=12,
        tool_result_max_chars=4000,
    )
    return Session(loop, ToolContext(backend=FakeBackend().client)), llm


def test_vegetarian_starters_under_400() -> None:
    args = {"category": "starter", "tags_any": ["vegetarian"], "max_price": 400}
    session, llm = session_for(
        [
            LLMResponse(tool_calls=[ToolCall(id="1", name="list_menu", arguments=args)]),
            LLMResponse(text="Paneer Tikka, Hara Bhara Kabab and Samosa."),
        ]
    )
    reply = session.send("What vegetarian starters do you have under 400?")
    assert reply.stop_reason == "answered" and "Samosa" in reply.text
    requested = [e for e in reply.events if isinstance(e, ToolRequested)]
    assert requested[0].name == "list_menu" and requested[0].arguments == args
    tool_content = llm.calls[1].messages[-1].tool_outcomes[0].content
    assert "Chicken Tikka" not in tool_content and "Samosa" in tool_content


def test_llm_outage_gives_honest_fallback() -> None:
    session, _ = session_for([LLMError("down")])
    reply = session.send("hi")
    assert reply.stop_reason == "llm_error" and "trouble" in reply.text
