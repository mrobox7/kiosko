"""Rules-only input guard: empty, length, rate limit and session token budget."""

from collections import deque
from datetime import datetime, timedelta

from app.guards.base import GuardDecision


class RulesGuard:
    """One instance per session: it remembers recent turn times for the rate limit."""

    def __init__(self, *, max_chars: int, turns_per_min: int, token_budget: int) -> None:
        self._max_chars = max_chars
        self._turns_per_min = turns_per_min
        self._token_budget = token_budget
        self._turns: deque[datetime] = deque()

    def check(self, text: str, *, now: datetime, tokens_used: int) -> GuardDecision:
        """Refuse empty, over-long, too-frequent messages and over-budget sessions."""
        if not text.strip():
            return GuardDecision(
                action="refuse", reason="empty", reply="Please type a message and I will help."
            )
        if len(text) > self._max_chars:
            return GuardDecision(
                action="refuse",
                reason="too_long",
                reply=f"Message too long. Please keep it under {self._max_chars} characters.",
            )
        if tokens_used >= self._token_budget:
            return GuardDecision(
                action="refuse",
                reason="token_budget",
                reply="This chat has reached its limit. Please start a new chat.",
            )
        while self._turns and now - self._turns[0] >= timedelta(minutes=1):
            self._turns.popleft()
        if len(self._turns) >= self._turns_per_min:
            return GuardDecision(
                action="refuse",
                reason="rate_limit",
                reply="You are sending messages too quickly. Please wait a moment.",
            )
        self._turns.append(now)
        return GuardDecision(action="pass")
