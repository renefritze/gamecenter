"""The settings subscreen: fullscreen toggle, backend choice, buzzer test."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from gamecenter.config.models import VALID_BACKENDS
from gamecenter.ui import ScreenName

if TYPE_CHECKING:
    from gamecenter.ui.app import GameCenterApp


class SettingsScreen(Screen):
    """Adjust app settings and reach the buzzer test."""

    def __init__(self, app: GameCenterApp, **kwargs) -> None:
        super().__init__(**kwargs)
        self._app = app
        root = BoxLayout(orientation="vertical", padding=16, spacing=12)

        bar = BoxLayout(size_hint_y=None, height=64, spacing=8)
        back = Button(text="< Back", size_hint_x=None, width=160, font_size="20sp")
        back.bind(on_release=lambda *_: self._app.goto(ScreenName.LAUNCHER))
        bar.add_widget(back)
        bar.add_widget(Label(text="Settings", font_size="24sp", bold=True))
        root.add_widget(bar)

        root.add_widget(Label(text="Buzzer backend", font_size="20sp", size_hint_y=None, height=40))
        backend_row = BoxLayout(size_hint_y=None, height=64, spacing=8)
        self._backend_buttons: dict[str, Button] = {}
        for name in VALID_BACKENDS:
            button = Button(text=name, font_size="18sp")
            button.bind(on_release=lambda _btn, n=name: self._select_backend(n))
            self._backend_buttons[name] = button
            backend_row.add_widget(button)
        root.add_widget(backend_row)

        self._fullscreen_button = Button(text="", size_hint_y=None, height=64, font_size="18sp")
        self._fullscreen_button.bind(on_release=lambda *_: self._toggle_fullscreen())
        root.add_widget(self._fullscreen_button)

        test = Button(text="Test / map buzzers", size_hint_y=None, height=72, font_size="20sp")
        test.bind(on_release=lambda *_: self._app.goto(ScreenName.BUZZER_TEST))
        root.add_widget(test)

        root.add_widget(BoxLayout())  # spacer
        self.add_widget(root)

    def on_pre_enter(self, *_args) -> None:
        self._refresh()

    def _refresh(self) -> None:
        config = self._app.settings.config
        for name, button in self._backend_buttons.items():
            button.background_color = (0.2, 0.6, 1, 1) if name == config.buzzers.backend else (1, 1, 1, 1)
        self._fullscreen_button.text = f"Fullscreen: {'ON' if config.fullscreen else 'OFF'}"

    def _select_backend(self, name: str) -> None:
        self._app.set_backend(name)
        self._refresh()

    def _toggle_fullscreen(self) -> None:
        self._app.set_fullscreen(enabled=not self._app.settings.config.fullscreen)
        self._refresh()
