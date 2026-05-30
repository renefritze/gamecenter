"""Kivy UI layer. Everything that imports Kivy lives under this subpackage."""

from __future__ import annotations

from enum import Enum


class ScreenName(str, Enum):
    """Stable names for the screens in the app's ScreenManager."""

    LAUNCHER = "launcher"
    SETTINGS = "settings"
    BUZZER_TEST = "buzzer_test"
    GAME_HOST = "game_host"
