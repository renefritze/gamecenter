"""Headless GUI smoke test for the Spotify Buzzer widget.

Marked ``gui`` so it is deselected by the default ``-m 'not gui'`` addopts; run
under a virtual display, e.g. ``xvfb-run -a pytest -m gui``. Uses the in-process
fake Spotify (``GAMECENTER_FAKE_SPOTIFY``) so no credentials or network are
needed, and avoids the threaded playlist fetch by feeding tracks straight into
the session, exercising every render path plus buzzer handling and scoring.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")

pytestmark = pytest.mark.gui


@pytest.fixture
def widget(monkeypatch):
    monkeypatch.setenv("GAMECENTER_FAKE_SPOTIFY", "1")
    from gamecenter.config.service import SettingsService
    from gamecenter.core.game_api import GameContext
    from gamecenter.core.registry import ServiceRegistry
    from gamecenter.games.spotify_buzzer.widget import SpotifyBuzzerWidget
    from gamecenter.input.manager import BuzzerManager

    try:
        settings = SettingsService()
        settings.load()
        context = GameContext(
            buzzers=BuzzerManager(settings.config.buzzers),
            settings=settings,
            services=ServiceRegistry(),
            players=settings.config.players,
            on_finish=lambda _result: None,
        )
        instance = SpotifyBuzzerWidget(context)
    except Exception as exc:  # pragma: no cover - environment without a usable window
        pytest.skip(f"No usable Kivy window provider: {exc}")
    instance.begin()
    yield instance
    instance.shutdown()


def _event(buzzer_index):
    from gamecenter.core.events import ButtonKind, BuzzerEvent

    return BuzzerEvent(device_id="kbd", buzzer_index=buzzer_index, button=ButtonKind.BUZZ, timestamp=0.0, raw=None)


def test_full_flow_through_widget(widget):
    from gamecenter.games.spotify_buzzer.logic import Phase
    from gamecenter.games.spotify_buzzer.widget import _FakeSpotify

    session = widget._session
    assert session.phase is Phase.JOIN

    widget.handle_buzzer(_event(0))
    widget.handle_buzzer(_event(1))
    assert len(session.players()) == 2

    widget._start_game()
    assert session.phase is Phase.PICK_PLAYLIST

    # Feed the playlist directly (skips the threaded fetch) and render PLAYING.
    tracks = _FakeSpotify().get_playlist_tracks("fake-80s")
    assert session.set_playlist(tracks) is True
    widget._render()
    assert session.phase is Phase.PLAYING

    # First player buzzes, host reveals, then scores artist+title + exact year.
    widget.handle_buzzer(_event(0))
    assert session.phase is Phase.ANSWERING
    widget._reveal_now()
    assert session.phase is Phase.REVEAL
    widget._confirm_score(artist_title=True, year_exact=True, year_close=False)
    assert session.phase is Phase.BETWEEN_ROUNDS
    assert session.scores()[1] == 4  # 1 (artist+title) + 3 (year exact)


def test_unconfigured_renders_without_service(monkeypatch):
    monkeypatch.delenv("GAMECENTER_FAKE_SPOTIFY", raising=False)
    from gamecenter.config.service import SettingsService
    from gamecenter.core.game_api import GameContext
    from gamecenter.core.registry import ServiceRegistry
    from gamecenter.games.spotify_buzzer.widget import SpotifyBuzzerWidget
    from gamecenter.input.manager import BuzzerManager

    try:
        settings = SettingsService()
        settings.load()
        context = GameContext(
            buzzers=BuzzerManager(settings.config.buzzers),
            settings=settings,
            services=ServiceRegistry(),
            players=settings.config.players,
            on_finish=lambda _result: None,
        )
        instance = SpotifyBuzzerWidget(context)
    except Exception as exc:  # pragma: no cover - environment without a usable window
        pytest.skip(f"No usable Kivy window provider: {exc}")
    instance.begin()  # no service registered -> should render the "not configured" panel
    assert instance._session is None
