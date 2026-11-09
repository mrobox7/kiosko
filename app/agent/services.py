"""What the nodes share and never change."""

from dataclasses import dataclass

from app.backend.client import BackendClient
from app.backend.models import Outlet
from app.llm.contract import LLMClient
from app.menu.menu import Menu
from app.tools.contract import Clock


@dataclass(frozen=True)
class Services:
    backend: BackendClient
    menu: Menu
    llm: LLMClient
    clock: Clock
    outlet: Outlet
    max_chars: int = 1000
    turns_per_min: int = 10
    token_budget: int = 200_000

    @property
    def outlet_code(self) -> str:
        return self.outlet.code
