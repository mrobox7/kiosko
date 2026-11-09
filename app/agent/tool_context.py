"""Between the chat state and the tools: the context a tool runs in is built from the state, and the
state fields a tool changed are read back from it."""

from typing import Any

from app.agent.services import Services
from app.agent.state import State
from app.tools.contract import ToolContext, ToolResult
from app.tools.registry import ToolRegistry


def tool_context(state: State, services: Services) -> ToolContext:
    return ToolContext(
        backend=services.backend,
        clock=services.clock,
        outlet_code=services.outlet_code,
        menu=services.menu,
        order=state.get("order"),
        customer=state.get("customer"),
        usual=tuple(state.get("usual", [])),
        allergies=tuple(state.get("allergies", [])),
        veg_only=state.get("veg_only", False),
    )


def run_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> tuple[ToolResult, ToolContext]:
    """Run one tool; the result, and the context once what it changed has happened."""
    result = ToolRegistry.shared().dispatch(name, args, ctx)
    return result, ctx.after(result.update)


def state_of(ctx: ToolContext) -> dict[str, Any]:
    return {
        "order": ctx.order,
        "customer": ctx.customer,
        "usual": list(ctx.usual),
        "allergies": list(ctx.allergies),
        "veg_only": ctx.veg_only,
    }
