"""The Spotify Buzzer game plugin.

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


class SpotifyBuzzerGame(BaseGame):
    """Play a random track from a Spotify playlist; first to buzz answers."""

    meta = GameMeta(
        id="spotify_buzzer",
        title="Spotify Buzzer",
        description="Name the song! A random track plays - buzz in, answer, and steal on a miss.",
        needs_buzzers=True,
        min_players=1,
        max_players=None,
    )

    def __init__(self) -> None:
        super().__init__()
        self._widget: Any = None

    def build_widget(self, context: GameContext) -> Any:
        from gamecenter.games.spotify_buzzer.widget import SpotifyBuzzerWidget

        self._widget = SpotifyBuzzerWidget(context)
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
GAME = SpotifyBuzzerGame
