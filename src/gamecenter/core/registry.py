"""In-package registries for games and services.

Games are bundled inside the package, so a simple registry beats Python
entry-points: it is explicit, fully testable and needs no display.
``GameRegistry.load_builtin()`` imports the built-in game modules and collects
their registered classes; construct a fresh registry per test to avoid global
state. (An entry-point loader for third-party games could be added later
without changing the metadata abstraction.)
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gamecenter.core.game_api import Game, GameMeta
    from gamecenter.core.service_api import Service

logger = logging.getLogger(__name__)

# Built-in game modules. Each defines a single Game subclass named GAME.
_BUILTIN_GAME_MODULES = (
    "gamecenter.games.quiz.game",
    "gamecenter.games.reaction.game",
    "gamecenter.games.spotify_buzzer.game",
)


class GameRegistry:
    """Holds the available game classes, keyed by their metadata id."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._games: dict[str, type[Game]] = {}

    def register(self, game_cls: type[Game]) -> type[Game]:
        """Register a game class; usable as a decorator."""
        self._games[game_cls.meta.id] = game_cls
        return game_cls

    def load_builtin(self) -> None:
        """Import and register the built-in games."""
        for module_name in _BUILTIN_GAME_MODULES:
            module = importlib.import_module(module_name)
            self.register(module.GAME)

    def all(self) -> list[GameMeta]:
        """Return all registered game metadata, sorted by title."""
        return sorted((cls.meta for cls in self._games.values()), key=lambda meta: meta.title)

    def create(self, game_id: str) -> Game:
        """Instantiate the game registered under ``game_id``."""
        return self._games[game_id]()


class ServiceRegistry:
    """Holds long-lived service instances, keyed by their id."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._services: dict[str, Service] = {}

    def register(self, service: Service) -> None:
        """Register a service instance."""
        self._services[service.id] = service

    def get(self, service_id: str) -> Service | None:
        """Return the service registered under ``service_id``, if any."""
        return self._services.get(service_id)

    def start_all(self) -> None:
        """Start every registered service."""
        for service in self._services.values():
            service.start()

    def stop_all(self) -> None:
        """Stop every registered service."""
        for service in self._services.values():
            service.stop()
