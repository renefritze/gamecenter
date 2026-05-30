"""The Reaction Test game plugin.

Kept Kivy-free at import time (so the registry loads headlessly); the widget is
imported lazily inside :meth:`build_widget`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gamecenter.core.game_api import GameMeta
from gamecenter.games.base import BaseGame

if TYPE_CHECKING:
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.core.game_api import GameContext


class ReactionGame(BaseGame):
    """Wait for GO, then measure each player's buzzer reaction time."""

    meta = GameMeta(
        id="reaction",
        title="Reaction Test",
        description="When the screen turns green, hit your buzzer as fast as you can!",
        needs_buzzers=True,
        min_players=1,
        max_players=4,
    )

    def __init__(self) -> None:
        super().__init__()
        self._widget: Any = None

    def build_widget(self, context: GameContext) -> Any:
        from gamecenter.games.reaction.widget import ReactionWidget

        self._widget = ReactionWidget(context)
        return self._widget

    def start(self, context: GameContext) -> None:
        super().start(context)
        if self._widget is not None:
            self._widget.begin()

    def stop(self) -> None:
        if self._widget is not None:
            self._widget.shutdown()
        super().stop()

    def on_buzzer_event(self, event: BuzzerEvent) -> None:
        if self._widget is not None:
            self._widget.handle_buzzer(event)


# Discovered by GameRegistry.load_builtin().
GAME = ReactionGame
