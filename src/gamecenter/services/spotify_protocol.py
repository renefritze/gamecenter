"""Shared, dependency-free contracts for the Spotify integration.

Defines the plain data types and :class:`typing.Protocol` interfaces that both
the game logic and the concrete :class:`~gamecenter.services.spotify.SpotifyService`
depend on. This module imports neither Kivy nor ``spotipy``, so the pure game
logic (:mod:`gamecenter.games.spotify_buzzer.logic`) and its headless tests can
import it without any optional dependency present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TrackInfo:
    """The minimal track metadata the game needs, decoupled from spotipy."""

    uri: str
    artist: str
    title: str
    year: int | None  # None when the release date precision yields no year
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PlaylistInfo:
    """A selectable playlist, decoupled from spotipy."""

    playlist_id: str
    name: str
    track_count: int


@runtime_checkable
class PlaybackController(Protocol):
    """The only playback side effects the pure game logic performs."""

    def play(self, uri: str, position_ms: int) -> None:
        """Start playing ``uri`` from ``position_ms``."""

    def resume(self) -> None:
        """Resume paused playback."""

    def pause(self) -> None:
        """Pause playback."""


@runtime_checkable
class PlaylistBrowser(Protocol):
    """Read-only playlist browsing used by the in-game picker."""

    def list_playlists(self) -> list[PlaylistInfo]:
        """Return the current user's playlists."""

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackInfo]:
        """Return the playable tracks of ``playlist_id``."""
