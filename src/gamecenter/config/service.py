"""Loading, saving and observing the persisted :class:`AppConfig`.

The service is tolerant of missing or corrupted data: anything it cannot parse
falls back to defaults, so a bad config file never prevents the app starting.
Writes are atomic (temp file + :func:`os.replace`).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from gamecenter.config.defaults import default_config
from gamecenter.config.models import (
    AppConfig,
    BuzzerConfig,
    PlayerSlot,
    ReactionConfig,
    SpotifyBuzzerConfig,
)
from gamecenter.paths import default_config_path

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

Observer = Callable[[AppConfig], None]


def _coerce_player(raw: Any, fallback: PlayerSlot) -> PlayerSlot:  # noqa: ANN401
    if not isinstance(raw, dict):
        return fallback
    return PlayerSlot(
        player_id=int(raw.get("player_id", fallback.player_id)),
        name=str(raw.get("name", fallback.name)),
        device_id=raw.get("device_id", fallback.device_id),
        buzzer_index=raw.get("buzzer_index", fallback.buzzer_index),
    )


def _coerce_buzzers(raw: Any, fallback: BuzzerConfig) -> BuzzerConfig:  # noqa: ANN401
    if not isinstance(raw, dict):
        return fallback
    keymap = raw.get("keymap")
    return BuzzerConfig(
        backend=str(raw.get("backend", fallback.backend)),
        keymap={str(k): int(v) for k, v in keymap.items()} if isinstance(keymap, dict) else fallback.keymap,
        keyboard_device_id=str(raw.get("keyboard_device_id", fallback.keyboard_device_id)),
    )


def _coerce_reaction(raw: Any, fallback: ReactionConfig) -> ReactionConfig:  # noqa: ANN401
    if not isinstance(raw, dict):
        return fallback
    return ReactionConfig(
        min_delay=float(raw.get("min_delay", fallback.min_delay)),
        max_delay=float(raw.get("max_delay", fallback.max_delay)),
        false_start_policy=str(raw.get("false_start_policy", fallback.false_start_policy)),
        penalty_ms=float(raw.get("penalty_ms", fallback.penalty_ms)),
        round_timeout=float(raw.get("round_timeout", fallback.round_timeout)),
    )


def _as(caster: Callable[[Any], Any], value: Any, fallback: Any) -> Any:  # noqa: ANN401
    """Cast ``value`` with ``caster``, returning ``fallback`` on bad input."""
    try:
        return caster(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_spotify_buzzer(raw: Any, fallback: SpotifyBuzzerConfig) -> SpotifyBuzzerConfig:  # noqa: ANN401
    if not isinstance(raw, dict):
        return fallback
    return SpotifyBuzzerConfig(
        position_mode=str(raw.get("position_mode", fallback.position_mode)),
        flash_timer_seconds=_as(float, raw.get("flash_timer_seconds"), fallback.flash_timer_seconds),
        points_artist_title=_as(int, raw.get("points_artist_title"), fallback.points_artist_title),
        points_year_exact=_as(int, raw.get("points_year_exact"), fallback.points_year_exact),
        points_year_close=_as(int, raw.get("points_year_close"), fallback.points_year_close),
        win_mode=str(raw.get("win_mode", fallback.win_mode)),
        target_points=_as(int, raw.get("target_points"), fallback.target_points),
        default_playlist_id=raw.get("default_playlist_id", fallback.default_playlist_id),
        timer_hard_cutoff=bool(raw.get("timer_hard_cutoff", fallback.timer_hard_cutoff)),
    )


def config_from_dict(raw: Any) -> AppConfig:  # noqa: ANN401
    """Build an :class:`AppConfig` from arbitrary loaded data, tolerantly."""
    base = default_config()
    if not isinstance(raw, dict):
        return base
    players_raw = raw.get("players")
    if isinstance(players_raw, list) and players_raw:
        players = [
            _coerce_player(item, base.players[min(i, len(base.players) - 1)]) for i, item in enumerate(players_raw)
        ]
    else:
        players = base.players
    return AppConfig(
        fullscreen=bool(raw.get("fullscreen", base.fullscreen)),
        buzzers=_coerce_buzzers(raw.get("buzzers"), base.buzzers),
        players=players,
        reaction=_coerce_reaction(raw.get("reaction"), base.reaction),
        spotify_buzzer=_coerce_spotify_buzzer(raw.get("spotify_buzzer"), base.spotify_buzzer),
    )


class SettingsService:
    """Owns the live :class:`AppConfig`, persistence and change notification."""

    def __init__(self, path: Path | None = None) -> None:
        """Create a service backed by ``path`` (defaults to the standard location)."""
        self._path = path or default_config_path()
        self._config = default_config()
        self._observers: list[Observer] = []

    @property
    def path(self) -> Path:
        """Path of the backing config file."""
        return self._path

    @property
    def config(self) -> AppConfig:
        """The current configuration."""
        return self._config

    def load(self) -> AppConfig:
        """Load config from disk, falling back to defaults on any error."""
        try:
            text = self._path.read_text(encoding="utf-8")
            raw = json.loads(text)
        except FileNotFoundError:
            logger.info("No config at %s; using defaults.", self._path)
            self._config = default_config()
        except (OSError, ValueError):
            logger.warning("Config at %s is unreadable; using defaults.", self._path, exc_info=True)
            self._config = default_config()
        else:
            self._config = config_from_dict(raw)
        return self._config

    def save(self) -> None:
        """Atomically persist the current config."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(self._config), indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".config-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, self._path)  # noqa: PTH105 - atomic rename of a temp fd path
        except OSError:
            if os.path.exists(tmp):  # noqa: PTH110
                os.unlink(tmp)  # noqa: PTH108
            raise

    def update(self, config: AppConfig) -> None:
        """Replace the config, persist it and notify observers."""
        self._config = config
        self.save()
        self._notify()

    def subscribe(self, observer: Observer) -> None:
        """Register a callback invoked after each :meth:`update`."""
        self._observers.append(observer)

    def unsubscribe(self, observer: Observer) -> None:
        """Remove a previously registered observer."""
        if observer in self._observers:
            self._observers.remove(observer)

    def _notify(self) -> None:
        for observer in self._observers:
            observer(self._config)
