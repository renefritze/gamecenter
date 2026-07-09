"""Spotify Web API playback and playlist service.

All network I/O for the Spotify Buzzer game lives here, behind the
:class:`~gamecenter.core.service_api.Service` contract. The ``spotipy`` library
(which implements the OAuth flow, on-disk token cache and automatic refresh) is
imported lazily, exactly like the hardware backends, so the package installs and
its tests run without the optional dependency. Public methods return the plain
dataclasses from :mod:`gamecenter.services.spotify_protocol`, never raw spotipy
objects, keeping the game logic and widget decoupled from the library.

Credentials are read from the environment (never at import time):
``SPOTIFY_CLIENT_ID``, ``SPOTIFY_CLIENT_SECRET`` and ``SPOTIFY_REDIRECT_URI``.
Controlling playback requires a Spotify Premium account and an active Spotify
Connect device (e.g. ``raspotify``/``librespot`` on the Pi).
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import TYPE_CHECKING, Any, ClassVar

from gamecenter.core.service_api import Service
from gamecenter.paths import config_dir
from gamecenter.services.spotify_protocol import PlaylistInfo, TrackInfo

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

ENV_CLIENT_ID = "SPOTIFY_CLIENT_ID"
ENV_CLIENT_SECRET = "SPOTIFY_CLIENT_SECRET"
ENV_REDIRECT_URI = "SPOTIFY_REDIRECT_URI"

# Scopes: read the user's playlists and read/control their playback.
_SCOPE = "playlist-read-private user-modify-playback-state user-read-playback-state"
# Spotify caps these list endpoints at 50 items per page.
_PAGE_LIMIT = 50


class SpotifyError(RuntimeError):
    """An actionable Spotify failure with a user-facing message."""


def _parse_year(release_date: str | None) -> int | None:
    """Extract a release year from an album ``release_date`` string.

    Spotify dates are ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD`` (per the album's
    ``release_date_precision``); the leading four digits are the year in every
    case. Returns ``None`` for missing or malformed values.
    """
    if not isinstance(release_date, str) or len(release_date) < 4:
        return None
    head = release_date[:4]
    return int(head) if head.isdigit() else None


def _to_track_info(item: dict[str, Any]) -> TrackInfo | None:
    """Convert a playlist item to :class:`TrackInfo`, or ``None`` if unplayable.

    Skips removed tracks, local files, podcast episodes and anything without a
    playable URI.
    """
    track = item.get("track") if isinstance(item, dict) else None
    if not isinstance(track, dict):
        return None
    if track.get("is_local") or track.get("type") not in (None, "track"):
        return None
    uri = track.get("uri")
    if not uri or not str(uri).startswith("spotify:track:"):
        return None
    artists = track.get("artists")
    artist = (
        artists[0].get("name", "") if isinstance(artists, list) and artists and isinstance(artists[0], dict) else ""
    )
    album = track.get("album") or {}
    return TrackInfo(
        uri=str(uri),
        artist=str(artist),
        title=str(track.get("name", "")),
        year=_parse_year(album.get("release_date") if isinstance(album, dict) else None),
        duration_ms=int(track.get("duration_ms", 0)),
    )


def _to_playlist_info(item: dict[str, Any]) -> PlaylistInfo | None:
    """Convert a Spotify playlist object to :class:`PlaylistInfo`."""
    playlist_id = item.get("id")
    if not playlist_id:
        return None
    tracks = item.get("tracks")
    track_count = int(tracks.get("total", 0)) if isinstance(tracks, dict) else 0
    return PlaylistInfo(
        playlist_id=str(playlist_id),
        name=str(item.get("name", "Untitled")),
        track_count=track_count,
    )


class SpotifyService(Service):
    """Long-lived Spotify Web API client shared with the Spotify Buzzer game."""

    id: ClassVar[str] = "spotify"

    def __init__(self, cache_path: Path | None = None, configured_playlist_ids: list[str] | None = None) -> None:
        """Create the service; ``cache_path`` overrides the token cache location."""
        self._cache_path = cache_path or (config_dir() / "spotify-token.json")
        self._configured_playlist_ids = tuple(dict.fromkeys(pid for pid in configured_playlist_ids or [] if pid))
        self._client: Any = None

    @classmethod
    def is_available(cls) -> bool:
        """Report whether credentials are set and ``spotipy`` is importable."""
        creds = all(os.environ.get(name) for name in (ENV_CLIENT_ID, ENV_CLIENT_SECRET, ENV_REDIRECT_URI))
        return bool(creds) and importlib.util.find_spec("spotipy") is not None

    def start(self) -> None:
        """Build the authenticated spotipy client (no-op if unavailable)."""
        if not self.is_available():
            logger.info("Spotify service unavailable; skipping start.")
            return
        try:
            import spotipy
            from spotipy.cache_handler import CacheFileHandler
            from spotipy.oauth2 import SpotifyOAuth

            auth = SpotifyOAuth(
                client_id=os.environ[ENV_CLIENT_ID],
                client_secret=os.environ[ENV_CLIENT_SECRET],
                redirect_uri=os.environ[ENV_REDIRECT_URI],
                scope=_SCOPE,
                cache_handler=CacheFileHandler(cache_path=str(self._cache_path)),
                open_browser=False,
            )
            self._client = spotipy.Spotify(auth_manager=auth)
        except Exception:
            logger.exception("Failed to start Spotify service; it will be inactive.")
            self._client = None

    def stop(self) -> None:
        """Release the client reference."""
        self._client = None

    @property
    def is_started(self) -> bool:
        """Whether an authenticated client is ready."""
        return self._client is not None

    # -- browsing -----------------------------------------------------------
    def list_playlists(self) -> list[PlaylistInfo]:
        """Return configured playlists followed by the current user's playlists."""
        client = self._require_client()
        playlists: list[PlaylistInfo] = []
        seen: set[str] = set()
        for playlist_id in self._configured_playlist_ids:
            try:
                item = client.playlist(playlist_id, fields="id,name,tracks.total")
            except Exception:
                logger.warning("Could not load configured Spotify playlist %s.", playlist_id, exc_info=True)
                continue
            if isinstance(item, dict) and (info := _to_playlist_info(item)) is not None:
                playlists.append(info)
                seen.add(info.playlist_id)

        offset = 0
        while True:
            page = client.current_user_playlists(limit=_PAGE_LIMIT, offset=offset)
            items = page.get("items", []) if isinstance(page, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                info = _to_playlist_info(item)
                if info is None or info.playlist_id in seen:
                    continue
                playlists.append(info)
                seen.add(info.playlist_id)
            if len(items) < _PAGE_LIMIT:
                break
            offset += _PAGE_LIMIT
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackInfo]:
        """Return the playable tracks of ``playlist_id`` (paginated)."""
        client = self._require_client()
        tracks: list[TrackInfo] = []
        offset = 0
        while True:
            page = client.playlist_items(
                playlist_id,
                limit=_PAGE_LIMIT,
                offset=offset,
                additional_types=("track",),
            )
            items = page.get("items", []) if isinstance(page, dict) else []
            for item in items:
                info = _to_track_info(item)
                if info is not None:
                    tracks.append(info)
            if len(items) < _PAGE_LIMIT:
                break
            offset += _PAGE_LIMIT
        return tracks

    # -- playback -----------------------------------------------------------
    def active_device(self) -> str | None:
        """Return the active (or first available) Connect device id, if any."""
        client = self._require_client()
        response = client.devices()
        devices = response.get("devices", []) if isinstance(response, dict) else []
        candidates = [d for d in devices if isinstance(d, dict) and d.get("id")]
        for device in candidates:
            if device.get("is_active"):
                return str(device["id"])
        return str(candidates[0]["id"]) if candidates else None

    def start_playback(self, uri: str, position_ms: int, device_id: str | None = None) -> None:
        """Play a single ``uri`` from ``position_ms`` on a Connect device."""
        client = self._require_client()
        target = device_id or self.active_device()
        if target is None:
            msg = "No active Spotify device. Open Spotify on a device and press play, then retry."
            raise SpotifyError(msg)
        self._call(client.start_playback, device_id=target, uris=[uri], position_ms=position_ms)

    def pause(self) -> None:
        """Pause playback (ignored if nothing is playing)."""
        client = self._require_client()
        self._call(client.pause_playback, ignore_status=(403, 404))

    def resume(self) -> None:
        """Resume the current playback."""
        client = self._require_client()
        self._call(client.start_playback, ignore_status=(403, 404))

    # -- internals ----------------------------------------------------------
    def _require_client(self) -> Any:
        if self._client is None:
            msg = "Spotify is not configured or failed to authenticate."
            raise SpotifyError(msg)
        return self._client

    @staticmethod
    def _call(func: Any, *, ignore_status: tuple[int, ...] = (), **kwargs: Any) -> None:
        """Call a spotipy method, translating its errors to :class:`SpotifyError`."""
        try:
            func(**kwargs)
        except Exception as exc:  # spotipy.SpotifyException, imported lazily
            status = getattr(exc, "http_status", None)
            if status in ignore_status:
                logger.debug("Ignoring Spotify %s on %s", status, getattr(func, "__name__", func))
                return
            if status == 403:
                msg = "Spotify Premium is required to control playback."
                raise SpotifyError(msg) from exc
            if status == 404:
                msg = "No active Spotify device. Open Spotify on a device and press play, then retry."
                raise SpotifyError(msg) from exc
            raise
