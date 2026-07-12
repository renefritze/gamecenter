"""Tests for the Spotify service helpers and availability (no network)."""

from __future__ import annotations

import importlib.util

import pytest

from gamecenter.services.spotify import (
    ENV_CLIENT_ID,
    ENV_CLIENT_SECRET,
    ENV_DEVICE_ID,
    ENV_DEVICE_NAME,
    ENV_LIBRESPOT_BINARY,
    ENV_LIBRESPOT_BITRATE,
    ENV_LOCAL_CONNECT_COMMAND,
    ENV_REDIRECT_URI,
    SpotifyError,
    SpotifyService,
    _parse_year,
    _to_track_info,
)

_ALL_ENV = (ENV_CLIENT_ID, ENV_CLIENT_SECRET, ENV_REDIRECT_URI)


# -- is_available ------------------------------------------------------------
def _set_creds(monkeypatch, *, present):
    for name in _ALL_ENV:
        if present:
            monkeypatch.setenv(name, "x")
        else:
            monkeypatch.delenv(name, raising=False)


def test_unavailable_without_credentials(monkeypatch):
    _set_creds(monkeypatch, present=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: object())
    assert SpotifyService.is_available() is False


def test_unavailable_without_spotipy(monkeypatch):
    _set_creds(monkeypatch, present=True)
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    assert SpotifyService.is_available() is False


def test_available_with_creds_and_spotipy(monkeypatch):
    _set_creds(monkeypatch, present=True)
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: object())
    assert SpotifyService.is_available() is True


def test_partial_credentials_are_unavailable(monkeypatch):
    _set_creds(monkeypatch, present=True)
    monkeypatch.delenv(ENV_REDIRECT_URI, raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: object())
    assert SpotifyService.is_available() is False


# -- year parsing ------------------------------------------------------------
@pytest.mark.parametrize(
    ("release_date", "expected"),
    [
        ("1994", 1994),
        ("1994-08", 1994),
        ("1994-08-21", 1994),
        ("0000-01-01", 0),
        ("", None),
        (None, None),
        ("abcd", None),
        ("19", None),
        (1994, None),  # non-string input must not raise
        (["1994"], None),
    ],
)
def test_parse_year(release_date, expected):
    assert _parse_year(release_date) == expected


# -- track conversion --------------------------------------------------------
def _item(**track_overrides):
    track = {
        "uri": "spotify:track:abc",
        "name": "Song",
        "type": "track",
        "duration_ms": 123_000,
        "artists": [{"name": "Band"}],
        "album": {"release_date": "1999-05-01"},
    }
    track.update(track_overrides)
    return {"track": track}


def test_to_track_info_happy_path():
    info = _to_track_info(_item())
    assert info is not None
    assert (info.uri, info.artist, info.title, info.year, info.duration_ms) == (
        "spotify:track:abc",
        "Band",
        "Song",
        1999,
        123_000,
    )


def test_to_track_info_skips_missing_track():
    assert _to_track_info({"track": None}) is None


def test_to_track_info_skips_local_files():
    assert _to_track_info(_item(is_local=True)) is None


def test_to_track_info_skips_episodes():
    assert _to_track_info(_item(type="episode")) is None


def test_to_track_info_skips_uriless():
    assert _to_track_info(_item(uri=None)) is None


def test_to_track_info_unknown_year_is_none():
    info = _to_track_info(_item(album={"release_date": ""}))
    assert info is not None
    assert info.year is None


def test_to_track_info_tolerates_malformed_artists():
    info = _to_track_info(_item(artists="not-a-list"))
    assert info is not None
    assert info.artist == ""


# -- active device + client guard -------------------------------------------
class _FakeClient:
    def __init__(self, devices=None, *, configured=None, user_playlists=None):
        self._configured = configured or {}
        self._devices = devices
        self._user_playlists = user_playlists or []
        self.playback_calls = []
        self.pause_calls = []

    def playlist(self, playlist_id, fields=None):
        return self._configured[playlist_id]

    def current_user_playlists(self, limit, offset):
        return {"items": self._user_playlists[offset : offset + limit]}

    def devices(self):
        return {"devices": self._devices}

    def start_playback(self, **kwargs):
        self.playback_calls.append(kwargs)

    def pause_playback(self, **kwargs):
        self.pause_calls.append(kwargs)


def test_active_device_prefers_active():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "is_active": False}, {"id": "b", "is_active": True}])
    assert service.active_device() == "b"


def test_active_device_ignores_inactive_devices():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "is_active": False}])
    assert service.active_device() is None


def test_active_device_none_when_empty():
    service = SpotifyService()
    service._client = _FakeClient([])
    assert service.active_device() is None


def test_start_playback_rejects_inactive_devices_without_preference():
    client = _FakeClient([{"id": "a", "is_active": False, "volume_percent": 40}])
    service = SpotifyService()
    service._client = client

    with pytest.raises(SpotifyError, match="No active Spotify device"):
        service.start_playback("spotify:track:abc", 12_000)

    assert client.playback_calls == []


def test_start_playback_can_use_configured_device_id(monkeypatch):
    client = _FakeClient([{"id": "a", "is_active": False, "volume_percent": 40}])
    service = SpotifyService()
    service._client = client
    monkeypatch.setenv(ENV_DEVICE_ID, "a")

    service.start_playback("spotify:track:abc", 12_000)

    assert client.playback_calls == [{"device_id": "a", "uris": ["spotify:track:abc"], "position_ms": 12_000}]


def test_start_playback_can_use_configured_device_name(monkeypatch):
    client = _FakeClient(
        [
            {"id": "a", "name": "Living Room", "is_active": True, "volume_percent": 40},
            {"id": "b", "name": "GameCenter", "is_active": False, "volume_percent": 40},
        ]
    )
    service = SpotifyService()
    service._client = client
    monkeypatch.setenv(ENV_DEVICE_NAME, "GameCenter")

    service.start_playback("spotify:track:abc", 12_000)

    assert client.playback_calls == [{"device_id": "b", "uris": ["spotify:track:abc"], "position_ms": 12_000}]


def test_managed_local_player_defaults_to_gamecenter_device():
    client = _FakeClient(
        [
            {"id": "a", "name": "Living Room", "is_active": True, "volume_percent": 40},
            {"id": "b", "name": "GameCenter", "is_active": False, "volume_percent": 40},
        ]
    )
    service = SpotifyService()
    service._client = client
    service._local_connect_process = object()

    service.start_playback("spotify:track:abc", 12_000)

    assert client.playback_calls == [{"device_id": "b", "uris": ["spotify:track:abc"], "position_ms": 12_000}]


def test_local_connect_argv_prefers_explicit_command(monkeypatch):
    service = SpotifyService()
    monkeypatch.setenv(ENV_LOCAL_CONNECT_COMMAND, "librespot --name Custom --backend alsa")

    assert service._local_connect_argv() == ["librespot", "--name", "Custom", "--backend", "alsa"]


def test_local_connect_argv_builds_librespot_command(monkeypatch, tmp_path):
    service = SpotifyService()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv(ENV_LIBRESPOT_BINARY, "/usr/bin/librespot")
    monkeypatch.setenv(ENV_DEVICE_NAME, "GameCenter Test")
    monkeypatch.setenv(ENV_LIBRESPOT_BITRATE, "160")

    argv = service._local_connect_argv()

    assert argv == [
        "/usr/bin/librespot",
        "-n",
        "GameCenter Test",
        "-b",
        "160",
        "-c",
        str(tmp_path / "gamecenter" / "librespot"),
    ]
    assert (tmp_path / "gamecenter" / "librespot").is_dir()


def test_pause_and_resume_use_playback_device():
    client = _FakeClient([{"id": "a", "is_active": True, "volume_percent": 40}])
    service = SpotifyService()
    service._client = client

    service.start_playback("spotify:track:abc", 12_000)
    service.pause()
    service.resume()

    assert client.pause_calls == [{"device_id": "a"}]
    assert client.playback_calls[-1] == {"device_id": "a"}


def test_pause_requires_selected_playback_device():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "is_active": True, "volume_percent": 40}])

    with pytest.raises(SpotifyError, match="No GameCenter Spotify playback device"):
        service.pause()


def test_start_playback_rejects_zero_volume_device():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "name": "Kitchen", "is_active": True, "volume_percent": 0}])

    with pytest.raises(SpotifyError, match="0% volume"):
        service.start_playback("spotify:track:abc", 0)


def test_start_playback_rejects_restricted_device():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "name": "Kitchen", "is_active": True, "is_restricted": True}])

    with pytest.raises(SpotifyError, match="cannot be controlled"):
        service.start_playback("spotify:track:abc", 0)


def test_calls_without_client_raise_spotify_error():
    service = SpotifyService()
    with pytest.raises(SpotifyError):
        service.list_playlists()


def test_list_playlists_prepends_configured_playlists_and_dedupes():
    service = SpotifyService(
        configured_playlist_ids=["configured", "dupe"],
    )
    service._client = _FakeClient(
        configured={
            "configured": {"id": "configured", "name": "Configured", "tracks": {"total": 10}},
            "dupe": {"id": "dupe", "name": "Configured Dupe", "tracks": {"total": 20}},
        },
        user_playlists=[
            {"id": "dupe", "name": "User Dupe", "tracks": {"total": 21}},
            {"id": "user", "name": "User", "tracks": {"total": 30}},
        ],
    )

    playlists = service.list_playlists()

    assert [(playlist.playlist_id, playlist.name, playlist.track_count) for playlist in playlists] == [
        ("configured", "Configured", 10),
        ("dupe", "Configured Dupe", 20),
        ("user", "User", 30),
    ]
