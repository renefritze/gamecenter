"""Tests for the Spotify service helpers and availability (no network)."""

from __future__ import annotations

import importlib.util

import pytest

from gamecenter.services.spotify import (
    ENV_CLIENT_ID,
    ENV_CLIENT_SECRET,
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


# -- active device + client guard -------------------------------------------
class _FakeClient:
    def __init__(self, devices):
        self._devices = devices

    def devices(self):
        return {"devices": self._devices}


def test_active_device_prefers_active():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "is_active": False}, {"id": "b", "is_active": True}])
    assert service.active_device() == "b"


def test_active_device_falls_back_to_first():
    service = SpotifyService()
    service._client = _FakeClient([{"id": "a", "is_active": False}])
    assert service.active_device() == "a"


def test_active_device_none_when_empty():
    service = SpotifyService()
    service._client = _FakeClient([])
    assert service.active_device() is None


def test_calls_without_client_raise_spotify_error():
    service = SpotifyService()
    with pytest.raises(SpotifyError):
        service.list_playlists()
