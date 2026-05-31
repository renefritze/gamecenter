"""Gamecenter: a full-screen touchscreen launcher for buzzer party games.

This top-level module must stay free of any Kivy import so that ``import
gamecenter`` and the headless test suite never require a display.
"""

__author__ = """Rene Fritze"""
__email__ = "rene+anthropic@fritze.me"

try:
    from . import _version

    __version__ = _version.__version__
except ImportError:  # pragma: no cover - only before a build
    import warnings

    warnings.warn("version file not found; package may not be installed correctly", stacklevel=2)
    __version__ = "unknown"
