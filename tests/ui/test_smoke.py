"""Headless GUI smoke test for the Kivy app shell.

Marked ``gui`` so it is deselected by the default ``-m 'not gui'`` addopts;
run it under a virtual display, e.g. ``xvfb-run -a pytest -m gui``.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")

pytestmark = pytest.mark.gui


@pytest.fixture
def app():
    # Imported lazily so the non-gui suite never pulls in Kivy.
    from gamecenter.config.service import SettingsService
    from gamecenter.core.registry import GameRegistry, ServiceRegistry
    from gamecenter.input.manager import BuzzerManager
    from gamecenter.ui.app import GameCenterApp

    settings = SettingsService()
    settings.load()
    buzzers = BuzzerManager(settings.config.buzzers)
    registry = GameRegistry()
    registry.load_builtin()
    instance = GameCenterApp(settings, buzzers, registry, ServiceRegistry(), windowed=True)
    try:
        # build() returns the ScreenManager; App.root is only set by run().
        instance.root = instance.build()
    except Exception as exc:  # pragma: no cover - environment without a usable window
        pytest.skip(f"No usable Kivy window provider: {exc}")
    return instance


def test_screens_are_registered(app):
    assert set(app.root.screen_names) == {"launcher", "settings", "buzzer_test", "game_host"}


def test_launch_and_return(app):
    app.launch_game("reaction")
    assert app.root.current == "game_host"
    app.back_to_launcher()
    assert app.root.current == "launcher"
