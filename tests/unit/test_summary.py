from pydantic import BaseModel

from app.domain.messages import Message, ToolCall, ToolOutcome
from app.domain.results import ToolResult
from app.session.summary import (
    ASKED_MAX,
    SAID_MAX,
    SUMMARY_MAX_CHARS,
    render_summary,
    summarise_turn,
)
from app.tools.base import Tool, ToolContext
from app.tools.registry import ToolRegistry
from tests.support.builders import make_ctx


def messages() -> list[Message]:
    return [
        Message(role="assistant", tool_calls=[ToolCall(id="a", name="get_menu")]),
        Message(
            role="user",
            tool_outcomes=[ToolOutcome(call_id="a", content="{...}", compact="9 dishes: 1 X 10")],
        ),
        Message(role="assistant", text="Here you go"),
    ]


def test_turn_entry_pairs_calls_with_their_compact_lines() -> None:
    entry = summarise_turn(3, "show  the\nmenu", messages(), "Here you go")
    assert entry.render() == (
        'T3 asked: "show the menu" | get_menu -> 9 dishes: 1 X 10 | said: "Here you go"'
    )


def test_text_only_turn_has_no_calls() -> None:
    assert summarise_turn(1, "hi", [], "Hello!").render() == 'T1 asked: "hi" | said: "Hello!"'


def test_long_text_is_cut_the_customers_at_the_end_the_agents_at_the_start() -> None:
    entry = summarise_turn(1, "a" * 500, [], "b" * 500)
    assert len(entry.asked) == ASKED_MAX and entry.asked.endswith("…")
    assert len(entry.said) == SAID_MAX and entry.said.startswith("…")
    reply = "Here is the long list of things. " * 10 + "Medium or Large?"
    assert summarise_turn(1, "x", [], reply).said.endswith("Medium or Large?")  # the question
    assert summarise_turn(1, "a b", [], "c d").asked == "a b"  # short text is kept whole


def test_calls_the_order_already_shows_are_left_out_but_the_turn_still_used_tools() -> None:
    shown = [
        Message(role="assistant", tool_calls=[ToolCall(id="a", name="add_to_order")]),
        Message(
            role="user",
            tool_outcomes=[ToolOutcome(call_id="a", content="{}", compact="added", in_order=True)],
        ),
        Message(role="assistant", text="Added"),
    ]
    entry = summarise_turn(2, "one tikki", shown, "Added")
    assert entry.calls == [] and entry.used_tools
    assert not summarise_turn(1, "hi", [], "Hello!").used_tools


def test_the_block_never_passes_its_cap_and_the_newest_entry_stays() -> None:
    entries = [summarise_turn(n, "q" * 250, messages(), "a" * 140) for n in range(1, 9)]
    block = render_summary(entries)
    assert len(block) <= SUMMARY_MAX_CHARS
    assert "(" in block.splitlines()[1] and "earlier turns not shown)" in block.splitlines()[1]
    assert block.splitlines()[-1].startswith("T8 asked") and "T1 asked" not in block
    assert render_summary(entries[:2]).count("\n") == 2  # small enough: nothing hidden
    assert len(render_summary(entries[:1], limit=10)) > 10  # the newest is never dropped


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

    llm = FakeLLM([call("get_menu"), LLMResponse(text="done")])
    result = make_loop(llm).run("sys", [Message(role="user", text="menu")], make_ctx())
    outcome = result.new_messages[1].tool_outcomes[0]
    assert "menu categories" in outcome.compact
