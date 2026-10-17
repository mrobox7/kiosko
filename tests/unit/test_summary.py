from pydantic import BaseModel

from app.domain.messages import Message, ToolCall, ToolOutcome
from app.domain.results import ToolResult
from app.session.summary import ASKED_MAX, SAID_MAX, render_summary, summarise_turn
from app.tools.base import Tool, ToolContext
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx


def messages() -> list[Message]:
    return [
        Message(role="assistant", tool_calls=[ToolCall(id="a", name="list_menu")]),
        Message(
            role="user",
            tool_outcomes=[ToolOutcome(call_id="a", content="{...}", compact="9 dishes: 1 X 10")],
        ),
        Message(role="assistant", text="Here you go"),
    ]


def test_turn_entry_pairs_calls_with_their_compact_lines() -> None:
    entry = summarise_turn(3, "show  the\nmenu", messages(), "Here you go")
    assert entry.render() == (
        'T3 asked: "show the menu" | list_menu -> 9 dishes: 1 X 10 | said: "Here you go"'
    )


def test_text_only_turn_has_no_calls() -> None:
    assert summarise_turn(1, "hi", [], "Hello!").render() == 'T1 asked: "hi" | said: "Hello!"'


def test_long_text_is_cut() -> None:
    entry = summarise_turn(1, "a" * 500, [], "b" * 500)
    assert len(entry.asked) == ASKED_MAX and entry.asked.endswith("…")
    assert len(entry.said) == SAID_MAX


def test_render_block_is_empty_without_entries() -> None:
    assert render_summary([]) == ""
    block = render_summary([summarise_turn(1, "hi", [], "Hello!")])
    assert block.splitlines()[0].startswith("Earlier turns") and "T1 asked" in block


class _Args(BaseModel):
    pass


class _Broken(Tool[_Args]):
    name = "broken_compact"
    description = "x"
    args_model = _Args

    def run(self, ctx: ToolContext, args: _Args) -> ToolResult:
        return ToolResult.success({})

    def compact(self, result: ToolResult, args: _Args) -> str:
        raise KeyError("boom")


def test_registry_compact_never_raises() -> None:
    registry = ToolRegistry([_Broken()])
    assert registry.compact("broken_compact", {}, ToolResult.success({})) == "ok"
    failure = ToolResult.failure("unknown_tool", "x")
    assert registry.compact("nope", {}, failure) == "error: unknown_tool"


def test_loop_stores_the_compact_line_on_the_outcome() -> None:
    from app.llm.base import LLMResponse
    from app.llm.fake import FakeLLM
    from tests.scenarios.test_summary_flow import call
    from tests.support.builders import make_loop

    llm = FakeLLM([call("list_menu"), LLMResponse(text="done")])
    result = make_loop(llm).run("sys", [Message(role="user", text="menu")], make_ctx())
    outcome = result.new_messages[1].tool_outcomes[0]
    assert "dishes:" in outcome.compact
