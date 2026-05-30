"""Boilerplate base class for games.

Handles the common buzzer subscribe/unsubscribe lifecycle so a concrete game
only implements :meth:`build_widget` and :meth:`on_buzzer_event`. Kivy-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gamecenter.core.game_api import Game

if TYPE_CHECKING:
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.core.game_api import GameContext


class BaseGame(Game):
    """A game that auto-manages its buzzer subscription."""

    def __init__(self) -> None:
        """Create the game with no active context."""
        self._context: GameContext | None = None

    @property
    def context(self) -> GameContext | None:
        """The active game context, or ``None`` before :meth:`start`."""
        return self._context

    def start(self, context: GameContext) -> None:
        """Store the context and subscribe to buzzer events."""
        self._context = context
        context.buzzers.subscribe(self.on_buzzer_event)

    def stop(self) -> None:
        """Unsubscribe from buzzer events."""
        if self._context is not None:
            self._context.buzzers.unsubscribe(self.on_buzzer_event)
            self._context = None

    def on_buzzer_event(self, event: BuzzerEvent) -> None:
        """Handle a buzzer event. Override in subclasses; default is a no-op."""
