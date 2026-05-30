"""The game plugin contract.

:class:`GameMeta` is a plain dataclass with no Kivy dependency so the launcher
can enumerate games and build tiles headlessly. Only :meth:`Game.build_widget`
touches Kivy, and it imports it lazily.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from gamecenter.config.models import PlayerSlot
    from gamecenter.config.service import SettingsService
    from gamecenter.core.registry import ServiceRegistry
    from gamecenter.input.manager import BuzzerManager


@dataclass(frozen=True, slots=True)
class GameMeta:
    """Static, display-time metadata describing a game."""

    id: str
    title: str
    description: str
    needs_buzzers: bool
    icon: str | None = None
    min_players: int = 1
    max_players: int | None = None


@dataclass(frozen=True, slots=True)
class GameResult:
    """Outcome reported by a game when it finishes."""

    game_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GameContext:
    """Everything a game needs at runtime, injected by the launcher."""

    buzzers: BuzzerManager
    settings: SettingsService
    services: ServiceRegistry
    players: list[PlayerSlot]
    on_finish: Callable[[GameResult], None]


class Game(ABC):
    """A launchable game. Subclass :class:`gamecenter.games.base.BaseGame`."""

    meta: ClassVar[GameMeta]

    @abstractmethod
    def build_widget(self, context: GameContext) -> Any:  # noqa: ANN401
        """Build and return the game's root Kivy widget (untyped ``Any`` in the core)."""

    @abstractmethod
    def start(self, context: GameContext) -> None:
        """Begin the game (subscribe to buzzers, start the round)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the game and release any resources."""
