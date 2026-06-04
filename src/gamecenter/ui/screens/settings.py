"""The settings subscreen: fullscreen toggle, backend choice, buzzer test."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from gamecenter.config.models import VALID_BACKENDS
from gamecenter.ui import ScreenName, theme
from gamecenter.ui.theme import Panel, StyledButton

if TYPE_CHECKING:
    from gamecenter.ui.app import GameCenterApp


class SettingsScreen(Screen):
    """Adjust app settings and reach the buzzer test."""

    def __init__(self, app: GameCenterApp, **kwargs) -> None:
        super().__init__(**kwargs)
        self._app = app
        root = BoxLayout(orientation="vertical", padding=16, spacing=16)

        bar = Panel(size_hint_y=None, height=72, padding=(12, 8), spacing=12)
        back = StyledButton(text="< Back", variant="secondary", size_hint_x=None, width=160)
        back.bind(on_release=lambda *_: self._app.goto(ScreenName.LAUNCHER))
        bar.add_widget(back)
        bar.add_widget(Label(text="Settings", font_size="24sp", bold=True, color=theme.TEXT))
        root.add_widget(bar)

        root.add_widget(
            Label(text="Buzzer backend", font_size="20sp", color=theme.TEXT_MUTED, size_hint_y=None, height=40)
        )
        backend_row = BoxLayout(size_hint_y=None, height=64, spacing=12)
        self._backend_buttons: dict[str, StyledButton] = {}
        for name in VALID_BACKENDS:
            button = StyledButton(text=name, variant="secondary", font_size="18sp")
            button.bind(on_release=lambda _btn, n=name: self._select_backend(n))
            self._backend_buttons[name] = button
            backend_row.add_widget(button)
        root.add_widget(backend_row)

        self._fullscreen_button = StyledButton(text="", variant="secondary", size_hint_y=None, height=64, font_size="18sp")
        self._fullscreen_button.bind(on_release=lambda *_: self._toggle_fullscreen())
        root.add_widget(self._fullscreen_button)

        test = StyledButton(text="Test / map buzzers", variant="primary", size_hint_y=None, height=72)
        test.bind(on_release=lambda *_: self._app.goto(ScreenName.BUZZER_TEST))
        root.add_widget(test)

        root.add_widget(BoxLayout())  # spacer
        self.add_widget(root)

    def on_pre_enter(self, *_args) -> None:
        self._refresh()

    def _refresh(self) -> None:
        config = self._app.settings.config
        for name, button in self._backend_buttons.items():
            button.set_variant("primary" if name == config.buzzers.backend else "secondary")
        self._fullscreen_button.text = f"Fullscreen: {'ON' if config.fullscreen else 'OFF'}"
        self._fullscreen_button.set_variant("success" if config.fullscreen else "secondary")

    def _select_backend(self, name: str) -> None:
        self._app.set_backend(name)
        self._refresh()

    def _toggle_fullscreen(self) -> None:
        self._app.set_fullscreen(enabled=not self._app.settings.config.fullscreen)
        self._refresh()
