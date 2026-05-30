"""Factory for a fresh default configuration."""

from __future__ import annotations

from gamecenter.config.models import AppConfig


def default_config() -> AppConfig:
    """Return a brand-new :class:`AppConfig` populated with defaults."""
    return AppConfig()
