"""The supervisor graph of one turn, and the saver that keeps each chat between turns.

    guard -> supervisor -> (searcher) -> (executor) -> respond -> commit

The guard refuses a message or starts a chat. `supervisor` writes the item list. After it and after
the searcher, a router in code reads the item statuses: search what is unknown, run the changes
that are clear, or reply. A turn that is all chat goes from `supervisor` straight to `commit`; a
model that cannot be reached ends the turn at `supervisor`."""

import dataclasses
import inspect
from collections.abc import Callable, Hashable
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel

import app.agent.items as items_module
import app.agent.state as state_module
import app.agent.trace as trace_module
import app.backend.models as backend_models
from app.agent.nodes.commit import commit
from app.agent.nodes.executor import executor
from app.agent.nodes.guard import after_guard, guard
from app.agent.nodes.respond import respond
from app.agent.nodes.searcher import searcher
from app.agent.nodes.supervisor import after_supervisor, supervisor
from app.agent.router import next_step
from app.agent.services import Services
from app.agent.state import Input, Output, RunContext, State

Graph = CompiledStateGraph[State, RunContext, Input, Output]


def _saved_types() -> list[type]:
    """Every class that ends up in the saved state, so the saver may read them back."""
    found: list[type] = []
    for module in (backend_models, items_module, state_module, trace_module):
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and (
                issubclass(cls, BaseModel) or dataclasses.is_dataclass(cls)
            ):
                found.append(cls)
    return found


def make_saver() -> InMemorySaver:
    return InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=_saved_types()))


def _route(state: State) -> str:
    return next_step(state.get("items", []))


def build_graph(services: Services, saver: InMemorySaver) -> Graph:
    def with_services(
        node: Callable[[State, Services], dict[str, object]],
    ) -> Callable[[State], dict[str, object]]:
        def run(state: State) -> dict[str, object]:
            return node(state, services)

        return run

    def speak(state: State, runtime: Runtime[RunContext]) -> dict[str, Any]:
        on_text = (runtime.context or {}).get("on_text")
        return respond(state, services, on_text)

    builder = StateGraph(State, context_schema=RunContext, input_schema=Input, output_schema=Output)
    for name, node in {
        "guard": with_services(guard),
        "supervisor": with_services(supervisor),
        "searcher": with_services(searcher),
        "executor": with_services(executor),
    }.items():
        builder.add_node(name, node)  # type: ignore[call-overload]  # a typed-callable quirk
    builder.add_node("respond", speak)
    builder.add_node("commit", commit)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", after_guard, {"supervisor": "supervisor", "end": END})
    after: dict[Hashable, str] = {
        "searcher": "searcher",
        "executor": "executor",
        "respond": "respond",
    }
    builder.add_conditional_edges(
        "supervisor", after_supervisor, {**after, "commit": "commit", "end": END}
    )
    builder.add_conditional_edges("searcher", _route, after)
    builder.add_edge("executor", "respond")
    builder.add_edge("respond", "commit")
    builder.add_edge("commit", END)
    return builder.compile(checkpointer=saver)
