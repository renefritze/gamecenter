"""Resolution of per-user config and data directories.

Centralised here so the rest of the code never hand-rolls XDG logic.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

APP_NAME = "gamecenter"


def config_dir() -> Path:
    """Return the user config directory, creating it if needed."""
    path = Path(platformdirs.user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Return the user data directory, creating it if needed."""
    path = Path(platformdirs.user_data_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_config_path() -> Path:
    """Return the default path of the persisted config file."""
    return config_dir() / "config.json"
