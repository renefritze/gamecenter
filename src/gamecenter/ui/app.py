"""The Kivy application: window/kiosk setup, screen wiring and navigation.

Built by :func:`run_app`, which constructs the Kivy-free services first (so
they stay testable) and injects them. Kivy is imported only when this module is
imported, which the CLI does lazily.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager

from gamecenter.config.service import SettingsService
from gamecenter.core.game_api import GameContext, GameResult
from gamecenter.core.registry import GameRegistry, ServiceRegistry
from gamecenter.input.manager import BuzzerManager
from gamecenter.ui import ScreenName
from gamecenter.ui.screens.buzzer_test import BuzzerTestScreen
from gamecenter.ui.screens.game_host import GameHostScreen
from gamecenter.ui.screens.launcher import LauncherScreen
from gamecenter.ui.screens.settings import SettingsScreen

if TYPE_CHECKING:
    from pathlib import Path

    from gamecenter.config.models import AppConfig
    from gamecenter.core.game_api import Game

logger = logging.getLogger(__name__)


class GameCenterApp(App):
    """The touchscreen kiosk app."""

    def __init__(
        self,
        settings: SettingsService,
        buzzers: BuzzerManager,
        registry: GameRegistry,
        services: ServiceRegistry,
        *,
        windowed: bool,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.buzzers = buzzers
        self.registry = registry
        self.services = services
        self._windowed = windowed
        self._manager: ScreenManager | None = None
        self._host: GameHostScreen | None = None
        self._active_game: Game | None = None

    def build(self) -> ScreenManager:
        self._configure_window()
        manager = ScreenManager()
        manager.add_widget(LauncherScreen(self, name=ScreenName.LAUNCHER.value))
        manager.add_widget(SettingsScreen(self, name=ScreenName.SETTINGS.value))
        manager.add_widget(BuzzerTestScreen(self, name=ScreenName.BUZZER_TEST.value))
        self._host = GameHostScreen(self, name=ScreenName.GAME_HOST.value)
        manager.add_widget(self._host)
        self._manager = manager
        Window.bind(on_key_down=self._on_key_down)
        return manager

    def _configure_window(self) -> None:
        Config.set("kivy", "exit_on_escape", "0")
        if self._windowed:
            Window.fullscreen = False
            Window.show_cursor = True
        else:
            Window.fullscreen = "auto"
            Window.show_cursor = False

    def on_start(self) -> None:
        self.services.start_all()
        self.buzzers.start()

    def on_stop(self) -> None:
        self.buzzers.stop()
        self.services.stop_all()

    def _on_key_down(self, _window, _keycode, _scancode, codepoint, _modifiers) -> bool:
        if codepoint:
            self.buzzers.feed_key(codepoint)
        return False

    # -- navigation ---------------------------------------------------------
    def goto(self, screen: ScreenName) -> None:
        """Switch to ``screen``."""
        if self._manager is not None:
            self._manager.current = screen.value

    def launch_game(self, game_id: str) -> None:
        """Instantiate, host and start the game identified by ``game_id``."""
        game = self.registry.create(game_id)
        context = GameContext(
            buzzers=self.buzzers,
            settings=self.settings,
            services=self.services,
            players=self.settings.config.players,
            on_finish=self._on_game_finish,
        )
        widget = game.build_widget(context)
        if self._host is not None:
            self._host.host(widget)
        game.start(context)
        self._active_game = game
        self.goto(ScreenName.GAME_HOST)

    def back_to_launcher(self) -> None:
        """Stop the active game and return to the launcher."""
        if self._active_game is not None:
            self._active_game.stop()
            self._active_game = None
        if self._host is not None:
            self._host.clear()
        self.goto(ScreenName.LAUNCHER)

    def _on_game_finish(self, result: GameResult) -> None:
        logger.info("Game finished: %s", result.game_id)

    # -- settings actions ---------------------------------------------------
    def set_backend(self, name: str) -> None:
        """Persist and hot-swap the buzzer backend."""
        from dataclasses import replace

        config = self.settings.config
        try:
            self.buzzers.set_backend(name)
        except Exception:
            logger.exception("Failed to switch to backend %s; keeping current", name)
            return
        updated: AppConfig = replace(config, buzzers=replace(config.buzzers, backend=name))
        self.settings.update(updated)

    def set_fullscreen(self, *, enabled: bool) -> None:
        """Persist and apply the fullscreen setting."""
        from dataclasses import replace

        updated: AppConfig = replace(self.settings.config, fullscreen=enabled)
        self.settings.update(updated)
        Window.fullscreen = "auto" if enabled else False


def run_app(*, windowed: bool = False, backend_override: str | None = None, config_path: Path | None = None) -> None:
    """Build services and run the Kivy app."""
    settings = SettingsService(config_path)
    settings.load()
    if backend_override:
        from dataclasses import replace

        config = settings.config
        updated: AppConfig = replace(config, buzzers=replace(config.buzzers, backend=backend_override))
        settings.update(updated)

    buzzers = BuzzerManager(
        settings.config.buzzers,
        dispatch=lambda fn: Clock.schedule_once(lambda _dt: fn(), 0),
    )
    registry = GameRegistry()
    registry.load_builtin()
    services = ServiceRegistry()

    GameCenterApp(settings, buzzers, registry, services, windowed=windowed).run()
