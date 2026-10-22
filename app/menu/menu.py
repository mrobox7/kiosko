"""The outlet's whole menu, kept in memory so the agent can look things up without a request."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.backend.client import BackendClient
from app.backend.errors import BackendError
from app.backend.models import MenuCategory, MenuDish
from app.menu.outline import render_outline


@dataclass(frozen=True)
class _Loaded:
    version: str
    categories: tuple[MenuCategory, ...]
    dishes: tuple[MenuDish, ...]
    by_id: dict[int, MenuDish]
    outline: str


class Menu:
    """Every dish this outlet is selling, with its questions, meals, nutrition and allergens, and
    the outline written from it. One `Menu` is shared by all chats. It is reloaded only when the
    server says the menu changed, so checking it at the start of a chat costs one small request.

    The tools read it for names, ids, choices and filters. The model sees only the outline and
    whatever a tool returns from it. The server still checks every order, so a dish switched off
    since the last reload is refused there."""

    def __init__(self, backend: BackendClient, outlet_code: str) -> None:
        self._backend = backend
        self._outlet = outlet_code
        self._loaded: _Loaded | None = None  # swapped as one, so a reader never sees half of it

    def refresh(self) -> None:
        """Ask the server for the menu's version and reload the menu if it changed. If the server
        cannot be asked, the copy already held is kept; before there is one, the error is raised."""
        try:
            version = self._backend.get_catalog_version(self._outlet)
            if self._loaded is None or self._loaded.version != version:
                catalog = self._backend.get_catalog(self._outlet)
                dishes = tuple(catalog.dishes)
                self._loaded = _Loaded(
                    catalog.version,
                    tuple(catalog.categories),
                    dishes,
                    {d.id: d for d in dishes},
                    render_outline(dishes),
                )
        except BackendError:
            if self._loaded is None:
                raise

    def _held(self) -> _Loaded:
        if self._loaded is None:
            self.refresh()
        assert self._loaded is not None
        return self._loaded

    @property
    def version(self) -> str:
        """The menu's version as of the last reload; it changes whenever the menu does."""
        return self._held().version

    @property
    def categories(self) -> Sequence[MenuCategory]:
        """The menu sections, in menu order."""
        return self._held().categories

    @property
    def dishes(self) -> Sequence[MenuDish]:
        """Every dish, in menu order. No request, except the very first time."""
        return self._held().dishes

    def dish(self, dish_id: int) -> MenuDish | None:
        """The dish with this id, or None if the outlet is not selling it."""
        return self._held().by_id.get(dish_id)

    @property
    def outline(self) -> str:
        """The outline for the system prompt, as of the last reload."""
        return self._held().outline
