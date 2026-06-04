"""The launcher: a grid of game tiles plus a settings button."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from gamecenter.ui import ScreenName, theme
from gamecenter.ui.theme import Panel, StyledButton
from gamecenter.ui.widgets.tile import GameTile

if TYPE_CHECKING:
    from gamecenter.ui.app import GameCenterApp


class LauncherScreen(Screen):
    """Root screen showing the available games."""

    def __init__(self, app: GameCenterApp, **kwargs) -> None:
        super().__init__(**kwargs)
        self._app = app
        root = BoxLayout(orientation="vertical")

        bar = Panel(size_hint_y=None, height=72, padding=(20, 12), spacing=8)
        bar.add_widget(Label(text="Gamecenter", font_size="26sp", bold=True, halign="left", color=theme.TEXT))
        settings = StyledButton(text="Settings", variant="secondary", size_hint_x=None, width=180)
        settings.bind(on_release=lambda *_: self._app.goto(ScreenName.SETTINGS))
        bar.add_widget(settings)
        root.add_widget(bar)

        self._grid = GridLayout(cols=2, padding=24, spacing=24)
        root.add_widget(self._grid)
        self.add_widget(root)

    def on_pre_enter(self, *_args) -> None:
        """Rebuild tiles from the registry each time the launcher is shown."""
        self._grid.clear_widgets()
        for meta in self._app.registry.all():
            self._grid.add_widget(GameTile(meta, self._app.launch_game))
