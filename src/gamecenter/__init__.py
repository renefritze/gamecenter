"""Gamecenter: a full-screen touchscreen launcher for buzzer party games.

This top-level module must stay free of any Kivy import so that ``import
gamecenter`` and the headless test suite never require a display.
"""

__author__ = """Rene Fritze"""
__email__ = "rene+anthropic@fritze.me"

try:
    from . import _version

    __version__ = _version.__version__
except ImportError as e:  # pragma: no cover - only before a build
    print(f"version file could not be imported: {e}")  # noqa: T201
    __version__ = "unknown"
