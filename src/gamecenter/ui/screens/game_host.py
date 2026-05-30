"""A reusable screen that hosts whichever game is currently running."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen

if TYPE_CHECKING:
    from kivy.uix.widget import Widget

    from gamecenter.ui.app import GameCenterApp


class GameHostScreen(Screen):
    """Wraps the active game's widget with a persistent back bar."""

    def __init__(self, app: GameCenterApp, **kwargs) -> None:
        super().__init__(**kwargs)
        self._app = app
        root = BoxLayout(orientation="vertical")
        bar = BoxLayout(size_hint_y=None, height=64, padding=8, spacing=8)
        back = Button(text="< Back", size_hint_x=None, width=160, font_size="20sp")
        back.bind(on_release=lambda *_: self._app.back_to_launcher())
        bar.add_widget(back)
        root.add_widget(bar)
        self._content = BoxLayout()
        root.add_widget(self._content)
        self.add_widget(root)

    def host(self, widget: Widget) -> None:
        """Display ``widget`` as the running game."""
        self._content.clear_widgets()
        self._content.add_widget(widget)

    def clear(self) -> None:
        """Remove the hosted game widget."""
        self._content.clear_widgets()
