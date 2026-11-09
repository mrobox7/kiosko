"""The supervisor's second call: the reply, written from what became of each item. The model writes
the words; code adds the order summary, so no quantity or price in a reply is the model's."""

import logging
from collections.abc import Callable

from app.agent.context import (
    FALLBACK,
    has_news,
    history_messages,
    open_questions,
    render_people,
    turn_report,
)
from app.agent.order_summary import order_summary
from app.agent.prompts import RESPOND_PROMPT, VOICE_PROMPT, outlet_line
from app.agent.services import Services
from app.agent.state import State
from app.agent.trace import Tally
from app.llm.contract import LLMError
from app.llm.messages import Message

logger = logging.getLogger(__name__)

CLOSING = "Anything else, or shall I place your order?"


def respond(
    state: State, services: Services, on_text: Callable[[str], None] | None = None
) -> dict[str, object]:
    items = state.get("items", [])
    spoken = state.get("spoken", False)
    system = f"{RESPOND_PROMPT}\n\n{VOICE_PROMPT}" if spoken else RESPOND_PROMPT
    context = "\n\n".join(
        [
            f"Customer's language: {state.get('language', 'en')}",
            outlet_line(state.get("outlet", services.outlet)),
            *render_people(state),
            "TURN REPORT\n" + turn_report(items, state.get("order")),
        ]
    )
    messages = [
        *history_messages(state.get("history", [])),
        Message(role="system", text=context),
        Message(role="user", text=state["user_text"]),
    ]
    tally = Tally()
    summary = order_summary(state.get("order"), items, spoken)
    asked = " ".join(open_questions(items))
    said = ""
    if has_news(items) or not asked:  # with only questions to put, there is nothing to word
        try:
            for _ in range(2):  # a model that returns nothing is asked once more
                if on_text is not None:
                    response = tally.stream(services.llm, system, messages, on_text)
                else:
                    response = tally.complete(services.llm, system, messages)
                said = (response.text or "").strip()
                if said:
                    break
        except LLMError as exc:
            logger.warning("Respond call failed: %s", exc)
            return {"reply": FALLBACK["llm_error"], "stop_reason": "llm_error", **tally.changes()}
    if not said and not summary and not asked:
        return {"reply": FALLBACK["unclear"], "stop_reason": "unclear", **tally.changes()}
    gap = " " if spoken else "\n"
    order = state.get("order")
    # With the order shown, nothing left to choose and not yet placed, code asks what comes next.
    closing = (
        CLOSING
        if summary and not asked and order and order.status == "draft" and order.lines
        else ""
    )
    tail = gap.join(part for part in (summary, asked, closing) if part)
    if tail and on_text is not None:
        on_text(gap + tail if said else tail)  # the summary and the questions follow the words
    return {"reply": gap.join(p for p in (said, tail) if p), "stop_reason": "", **tally.changes()}
