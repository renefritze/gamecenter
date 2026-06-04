"""Dataclass models for persisted configuration.

These are plain, Kivy-free dataclasses. (De)serialisation lives in
:mod:`gamecenter.config.service`; the models only describe shape and defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Backend names understood by the buzzer factory.
BACKEND_AUTO = "auto"
BACKEND_KEYBOARD = "keyboard"
BACKEND_HIDAPI = "hidapi"
BACKEND_EVDEV = "evdev"
VALID_BACKENDS = (BACKEND_AUTO, BACKEND_KEYBOARD, BACKEND_HIDAPI, BACKEND_EVDEV)

# False-start handling policies for the reaction game.
POLICY_DISQUALIFY = "disqualify"
POLICY_PENALTY = "penalty"

# Spotify Buzzer playback start positions.
POSITION_START = "start"  # play from 0:00
POSITION_AFTER_30S = "after_30s"  # skip the intro, play from 0:30
POSITION_RANDOM = "random"  # a random point within the track
VALID_POSITION_MODES = (POSITION_START, POSITION_AFTER_30S, POSITION_RANDOM)

# Spotify Buzzer win modes.
WIN_INFINITE = "infinite"  # play forever, no automatic end
WIN_TARGET = "target"  # first player to reach target_points wins
VALID_WIN_MODES = (WIN_INFINITE, WIN_TARGET)


@dataclass(slots=True)
class PlayerSlot:
    """A player and the physical buzzer assigned to them (if any)."""

    player_id: int
    name: str
    device_id: str | None = None
    buzzer_index: int | None = None

    @property
    def is_mapped(self) -> bool:
        """Whether this slot has a physical buzzer assigned."""
        return self.device_id is not None and self.buzzer_index is not None

    @property
    def key(self) -> tuple[str, int] | None:
        """The ``(device_id, buzzer_index)`` key, or ``None`` if unmapped."""
        if self.device_id is None or self.buzzer_index is None:
            return None
        return (self.device_id, self.buzzer_index)


def _default_keymap() -> dict[str, int]:
    """Default keyboard fallback mapping: keys 1-4 -> buzzers 0-3."""
    return {"1": 0, "2": 1, "3": 2, "4": 3}


@dataclass(slots=True)
class BuzzerConfig:
    """Buzzer input configuration."""

    backend: str = BACKEND_AUTO
    # Maps a keyboard character to a buzzer index, used by the keyboard backend.
    keymap: dict[str, int] = field(default_factory=_default_keymap)
    # Stable device id used by the keyboard backend's synthetic events.
    keyboard_device_id: str = "keyboard"


@dataclass(slots=True)
class ReactionConfig:
    """Reaction-test game tuning."""

    min_delay: float = 2.0
    max_delay: float = 6.0
    false_start_policy: str = POLICY_DISQUALIFY
    penalty_ms: float = 1000.0
    round_timeout: float = 5.0


@dataclass(slots=True)
class SpotifyBuzzerConfig:
    """Spotify Buzzer (music quiz) game tuning."""

    position_mode: str = POSITION_START
    flash_timer_seconds: float = 10.0
    points_artist_title: int = 1
    points_year_exact: int = 3
    points_year_close: int = 1
    win_mode: str = WIN_INFINITE
    target_points: int = 15
    default_playlist_id: str | None = None
    # When True, the flash timer expiring locks the answerer out (hard cutoff);
    # when False (default) it just reveals so the host can still award points.
    timer_hard_cutoff: bool = False


def _default_players() -> list[PlayerSlot]:
    """Four unmapped player slots by default."""
    return [PlayerSlot(player_id=i, name=f"Player {i + 1}") for i in range(4)]


@dataclass(slots=True)
class AppConfig:
    """Top-level application configuration."""

    fullscreen: bool = True
    buzzers: BuzzerConfig = field(default_factory=BuzzerConfig)
    players: list[PlayerSlot] = field(default_factory=_default_players)
    reaction: ReactionConfig = field(default_factory=ReactionConfig)
    spotify_buzzer: SpotifyBuzzerConfig = field(default_factory=SpotifyBuzzerConfig)
