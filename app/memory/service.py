"""Load and save customer memory. Reads the backend; owns no state."""

import logging
from collections import Counter
from collections.abc import Sequence

from pydantic import ValidationError

from app.backend.client import BackendClient
from app.backend.errors import BackendError
from app.backend.models import MenuFilters
from app.memory.profile import CustomerProfile, OrderLine
from app.memory.schema import Preferences, merge_preferences

logger = logging.getLogger(__name__)
TOP_ORDERED = 3


class MemoryService:
    """Preferences live in the backend blob; favourites are derived from order history."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    def order_history(self, customer_id: int) -> list[OrderLine]:
        """The customer's ordered items on non-cancelled bookings, newest booking first."""
        bookings = {r.id: r for r in self._backend.list_customer_reservations(customer_id)}
        names = {i.id: i.name for i in self._backend.get_menu(MenuFilters(available_only=False))}
        lines = [
            (
                o.id,
                OrderLine(
                    reservation_id=o.reservation_id,
                    slot=bookings[o.reservation_id].slot_datetime,
                    status=bookings[o.reservation_id].status,
                    item=names.get(o.menu_item_id, f"item #{o.menu_item_id}"),
                    quantity=o.quantity,
                ),
            )
            for o in self._backend.list_customer_orders(customer_id)
            if o.reservation_id in bookings and bookings[o.reservation_id].status != "cancelled"
        ]
        lines.sort(key=lambda pair: (pair[1].slot, pair[0]), reverse=True)
        return [line for _, line in lines]

    def load_profile(self, customer_id: int, name: str = "") -> CustomerProfile:
        """Never raises: on any failure the profile is empty with `memory_unavailable` set."""
        try:
            customer = self._backend.get_customer(customer_id)
            totals: Counter[str] = Counter()
            for line in self.order_history(customer_id):
                totals[line.item] += line.quantity
        except BackendError, ValidationError:
            logger.warning("Could not load memory for customer %s", customer_id)
            return CustomerProfile(name=name, memory_unavailable=True)
        prefs = Preferences.from_blob(customer.preferences)
        top = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_ORDERED]
        return CustomerProfile(
            name=customer.name,
            seating=prefs.seating,
            dietary=prefs.dietary,
            allergies=prefs.allergies,
            most_ordered=[item for item, _ in top],
        )

    def read_preferences(self, customer_id: int) -> Preferences:
        """The customer's current stored preferences, read fresh from the backend."""
        return Preferences.from_blob(self._backend.get_customer(customer_id).preferences)

    def update_preferences(
        self,
        customer_id: int,
        *,
        seating: str | None = None,
        dietary_add: Sequence[str] = (),
        dietary_remove: Sequence[str] = (),
        allergies_add: Sequence[str] = (),
        allergies_remove: Sequence[str] = (),
    ) -> tuple[Preferences, bool]:
        """Apply explicit changes on top of what is stored. Returns (preferences, changed);
        nothing is written when nothing would change."""
        customer = self._backend.get_customer(customer_id)
        blob, changed = merge_preferences(
            customer.preferences,
            seating=seating,
            dietary_add=dietary_add,
            dietary_remove=dietary_remove,
            allergies_add=allergies_add,
            allergies_remove=allergies_remove,
        )
        if changed:
            customer = self._backend.patch_preferences(customer_id, blob)
        return Preferences.from_blob(customer.preferences), changed
