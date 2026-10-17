"""The distilled profile shown to the model and the UI."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.memory.schema import Allergen, Dietary, Seating


class OrderLine(BaseModel):
    """One ordered item with the booking it belongs to."""

    reservation_id: int
    slot: datetime
    status: str
    item: str
    quantity: int


class CustomerProfile(BaseModel):
    """What the agent remembers about a customer. Built only from whitelisted values,
    never from free text stored in the backend blob."""

    name: str = ""
    seating: Seating | None = None
    dietary: list[Dietary] = Field(default_factory=list)
    allergies: list[Allergen] = Field(default_factory=list)
    most_ordered: list[str] = Field(default_factory=list)
    memory_unavailable: bool = False

    def facts(self) -> list[tuple[str, str]]:
        """Label and value for every non-empty field. One source for prompt and sidebar."""
        out: list[tuple[str, str]] = []
        if self.seating:
            out.append(("Seating preference", self.seating))
        if self.dietary:
            out.append(("Dietary preference", ", ".join(self.dietary)))
        if self.allergies:
            out.append(("Allergies", ", ".join(self.allergies)))
        if self.most_ordered:
            out.append(("Most ordered", ", ".join(self.most_ordered)))
        return out

    def render(self) -> str:
        """The profile block for the system prompt."""
        if self.memory_unavailable:
            return (
                "Customer memory: unavailable right now. Do not claim to remember "
                "anything about this customer."
            )
        facts = self.facts()
        if not facts:
            return "Remembered about this customer: nothing yet."
        return "Remembered about this customer:\n" + "\n".join(f"- {k}: {v}" for k, v in facts)
