"""Scripted UI tour that drives the real app for screen recording.

Runs the actual Kivy event loop and steps through the screens on a timer
(launcher -> settings -> buzzer test -> Reaction game), simulating buzzer key
presses along the way, then stops itself. Intended to be captured with a screen
recorder under a virtual display (see ``.github/workflows/ui-video.yml``), but
also handy locally via ``gamecenter demo``.

Kept out of the import path of the headless suite: Kivy is imported only when
this module is imported, which the CLI does lazily.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kivy.app import App
from kivy.clock import Clock

from gamecenter.ui import ScreenName

if TYPE_CHECKING:
    from pathlib import Path

    from gamecenter.ui.app import GameCenterApp

logger = logging.getLogger(__name__)


def _press_all_buzzers(app: GameCenterApp) -> None:
    """Fire every mapped keyboard buzzer so indicators/scores light up."""
    for key in app.settings.config.buzzers.keymap:
        app.buzzers.feed_key(key)


def _build_scenario(app: GameCenterApp, step: float) -> None:
    """Schedule the timed tour. Each ``Clock`` callback ignores its dt arg."""
    # (delay-in-steps, action) pairs; actions exercise the real navigation API.
    actions = [
        (1, lambda: app.goto(ScreenName.SETTINGS)),
        (2, lambda: app.goto(ScreenName.BUZZER_TEST)),
        (3, lambda: _press_all_buzzers(app)),
        (4, lambda: app.goto(ScreenName.LAUNCHER)),
        (5, lambda: app.launch_game("reaction")),
        (7, lambda: _press_all_buzzers(app)),
        (8, lambda: _press_all_buzzers(app)),
        (9, app.back_to_launcher),
        (10, _stop),
    ]
    for steps, action in actions:
        Clock.schedule_once(lambda _dt, _a=action: _a(), steps * step)


def _stop(*_args) -> None:
    running = App.get_running_app()
    if running is not None:
        running.stop()


def run_demo(
    *,
    width: int = 1280,
    height: int = 720,
    backend_override: str | None = "keyboard",
    config_path: Path | None = None,
    step: float = 1.5,
) -> None:
    """Run the scripted UI tour and exit on its own.

    The window is sized to ``width`` x ``height`` so a screen-grab's resolution
    lines up with the window exactly. This must happen before Kivy's ``Window``
    is created, so the app (and its ``Window`` import) is pulled in lazily here
    after the config is set. The keyboard backend is forced by default so buzzer
    presses can be simulated.
    """
    from kivy.config import Config

    Config.set("graphics", "width", str(width))
    Config.set("graphics", "height", str(height))
    Config.set("graphics", "fullscreen", "0")
    Config.set("graphics", "borderless", "1")
    Config.set("graphics", "resizable", "0")

    # Imported only now so the Window is created with the config set above.
    from gamecenter.ui.app import build_app

    app = build_app(windowed=True, backend_override=backend_override, config_path=config_path)
    # Scenario callbacks run on the UI thread once the loop (and buzzers) are up.
    Clock.schedule_once(lambda _dt: _build_scenario(app, step), 0)
    app.run()
