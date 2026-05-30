"""A large, touch-friendly game tile for the launcher grid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

if TYPE_CHECKING:
    from collections.abc import Callable

    from gamecenter.core.game_api import GameMeta


class GameTile(ButtonBehavior, BoxLayout):
    """A tappable tile showing a game's title and description."""

    def __init__(self, meta: GameMeta, on_launch: Callable[[str], None], **kwargs) -> None:
        super().__init__(orientation="vertical", padding=20, spacing=10, **kwargs)
        self._game_id = meta.id
        self._on_launch = on_launch
        self.add_widget(Label(text=meta.title, font_size="32sp", bold=True))
        self.add_widget(Label(text=meta.description, font_size="18sp", halign="center", valign="middle"))
        if meta.needs_buzzers:
            self.add_widget(Label(text="[buzzers required]", font_size="14sp", color=(0.7, 0.7, 0.7, 1)))

    def on_release(self) -> None:
        self._on_launch(self._game_id)
