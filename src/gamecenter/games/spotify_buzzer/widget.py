"""Kivy view for the Spotify Buzzer game.

A thin layer over :class:`gamecenter.games.spotify_buzzer.logic.BuzzerSession`:
it owns the Kivy ``Clock`` (the flashing answer countdown and the threaded
playlist fetch), renders one panel per phase, and translates touches and buzzer
events into pure-logic calls. All Spotify access goes through the service (or an
in-process fake when ``GAMECENTER_FAKE_SPOTIFY`` is set), wrapped in a small
adapter that satisfies the logic's ``PlaybackController`` protocol so the logic
never imports Kivy or spotipy.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING, ClassVar

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from gamecenter.games.spotify_buzzer.logic import BuzzerSession, Phase, RevealMarks
from gamecenter.services.spotify import SpotifyError
from gamecenter.services.spotify_protocol import PlaylistInfo, TrackInfo
from gamecenter.ui import theme
from gamecenter.ui.theme import Panel, StyledButton

if TYPE_CHECKING:
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.core.game_api import GameContext

logger = logging.getLogger(__name__)

_ENV_FAKE = "GAMECENTER_FAKE_SPOTIFY"

# Full-screen background tints per phase.
_BG_NEUTRAL = theme.BACKGROUND
_BG_PLAYING = (0.105, 0.122, 0.200, 1)
_BG_FLASH_A = (0.690, 0.180, 0.180, 1)
_BG_FLASH_B = (0.180, 0.208, 0.318, 1)
_BG_DONE = (0.137, 0.161, 0.255, 1)


class _PlaybackAdapter:
    """Adapts the Spotify service to the logic's ``PlaybackController``.

    Swallows :class:`SpotifyError` into a UI callback so a missing device or a
    non-Premium account never crashes the (UI-thread) logic call.
    """

    def __init__(self, service, on_error) -> None:
        self._service = service
        self._on_error = on_error

    def play(self, uri: str, position_ms: int) -> None:
        self._guard(lambda: self._service.start_playback(uri, position_ms))

    def resume(self) -> None:
        self._guard(self._service.resume)

    def pause(self) -> None:
        self._guard(self._service.pause)

    def _guard(self, action) -> None:
        try:
            action()
        except SpotifyError as exc:
            self._on_error(str(exc))
        except Exception:
            logger.exception("Unexpected Spotify playback error")
            self._on_error("Spotify playback failed; check the device and try again.")


class _FakeSpotify:
    """An in-process stand-in for dry runs without credentials or Premium."""

    _PLAYLISTS = (
        PlaylistInfo("fake-80s", "Demo: 80s Classics", 3),
        PlaylistInfo("fake-indie", "Demo: Indie Mix", 2),
    )
    _TRACKS: ClassVar[dict[str, tuple[TrackInfo, ...]]] = {
        "fake-80s": (
            TrackInfo("spotify:track:fake1", "a-ha", "Take On Me", 1985, 225_000),
            TrackInfo("spotify:track:fake2", "Toto", "Africa", 1982, 295_000),
            TrackInfo("spotify:track:fake3", "Queen", "Under Pressure", 1981, 248_000),
        ),
        "fake-indie": (
            TrackInfo("spotify:track:fake4", "Arctic Monkeys", "Do I Wanna Know?", 2013, 272_000),
            TrackInfo("spotify:track:fake5", "The Strokes", "Last Nite", 2001, 192_000),
        ),
    }

    def list_playlists(self) -> list[PlaylistInfo]:
        return list(self._PLAYLISTS)

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackInfo]:
        return list(self._TRACKS.get(playlist_id, ()))

    def start_playback(self, uri: str, position_ms: int, device_id: str | None = None) -> None:
        logger.info("FakeSpotify play %s @ %dms (device=%s)", uri, position_ms, device_id)

    def pause(self) -> None:
        logger.info("FakeSpotify pause")

    def resume(self) -> None:
        logger.info("FakeSpotify resume")


class SpotifyBuzzerWidget(BoxLayout):
    """Renders the Spotify Buzzer session, one panel per phase."""

    def __init__(self, context: GameContext, **kwargs) -> None:
        super().__init__(orientation="vertical", padding=16, spacing=12, **kwargs)
        self._context = context
        self._service = self._resolve_service(context)
        self._session: BuzzerSession | None = None
        self._countdown_event = None
        self._answer_deadline: float | None = None
        self._countdown_label: Label | None = None

        with self.canvas.before:
            self._bg_color = Color(*_BG_NEUTRAL)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        self._banner = Label(text="", font_size="18sp", color=theme.DANGER, size_hint_y=None, height=0)
        self._content = BoxLayout(orientation="vertical", spacing=12)
        self.add_widget(self._banner)
        self.add_widget(self._content)

    # -- service wiring -----------------------------------------------------
    @staticmethod
    def _resolve_service(context: GameContext):
        if os.environ.get(_ENV_FAKE):
            logger.info("Spotify Buzzer using the in-process fake (GAMECENTER_FAKE_SPOTIFY).")
            return _FakeSpotify()
        return context.services.get("spotify")

    # -- lifecycle ----------------------------------------------------------
    def begin(self) -> None:
        if self._service is None:
            self._render_unconfigured()
            return
        config = self._context.settings.config.spotify_buzzer
        playback = _PlaybackAdapter(self._service, self._show_error)
        self._session = BuzzerSession(config, playback, known_players=self._context.players)
        self._render()

    def shutdown(self) -> None:
        self._cancel_countdown()

    # -- buzzer input -------------------------------------------------------
    def handle_buzzer(self, event: BuzzerEvent) -> None:
        session = self._session
        if session is None:
            return
        if session.phase is Phase.JOIN:
            if session.join_buzz(event.device_id, event.buzzer_index) is not None:
                self._render_join()
        elif session.phase is Phase.PLAYING:
            player = session.player_for(event.device_id, event.buzzer_index)
            if player is not None and session.buzz(player.player_id):
                self._enter_answering()

    # -- rendering dispatch -------------------------------------------------
    def _render(self) -> None:
        self._cancel_countdown()
        phase = self._session.phase if self._session else None
        if phase is Phase.JOIN:
            self._render_join()
        elif phase is Phase.PICK_PLAYLIST:
            self._render_pick_playlist()
        elif phase is Phase.PLAYING:
            self._render_playing()
        elif phase is Phase.REVEAL:
            self._render_reveal()
        elif phase is Phase.BETWEEN_ROUNDS:
            self._render_between_rounds()
        elif phase is Phase.GAME_OVER:
            self._render_game_over()

    def _fresh_content(self, title: str, bg) -> BoxLayout:
        self._content.clear_widgets()
        self._set_bg(bg)
        self._content.add_widget(
            Label(text=title, font_size="36sp", bold=True, color=theme.TEXT, size_hint_y=None, height=64)
        )
        return self._content

    # -- phases -------------------------------------------------------------
    def _render_unconfigured(self) -> None:
        body = self._fresh_content("Spotify not configured", _BG_NEUTRAL)
        body.add_widget(
            Label(
                text=(
                    "Set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET and SPOTIFY_REDIRECT_URI\n"
                    "and install the optional 'spotify' extra, then restart.\n"
                    "Or set GAMECENTER_FAKE_SPOTIFY=1 for an offline dry run."
                ),
                font_size="20sp",
                color=theme.TEXT_MUTED,
            )
        )

    def _render_join(self) -> None:
        session = self._session
        body = self._fresh_content("Press your buzzer to join", _BG_NEUTRAL)
        players = session.players() if session else []
        roster = "\n".join(f"{p.display_name}" for p in players) or "No players yet..."
        body.add_widget(Label(text=roster, font_size="24sp", color=theme.TEXT))
        start = StyledButton(text="Start game", variant="success", size_hint_y=None, height=72)
        start.disabled = not players
        start.bind(on_release=lambda *_: self._start_game())
        body.add_widget(start)

    def _start_game(self) -> None:
        if self._session and self._session.finish_join():
            self._render()

    def _render_pick_playlist(self) -> None:
        body = self._fresh_content("Loading playlists...", _BG_NEUTRAL)
        body.add_widget(Label(text="Fetching your Spotify playlists", font_size="20sp", color=theme.TEXT_MUTED))
        threading.Thread(target=self._load_playlists, daemon=True).start()

    def _load_playlists(self) -> None:
        try:
            playlists = self._service.list_playlists()
            error = None
        except SpotifyError as exc:
            playlists, error = [], str(exc)
        except Exception:
            logger.exception("Failed to list playlists")
            playlists, error = [], "Could not load playlists; check Spotify and retry."
        Clock.schedule_once(lambda _dt: self._show_playlists(playlists, error), 0)

    def _show_playlists(self, playlists: list[PlaylistInfo], error: str | None) -> None:
        if self._session is None or self._session.phase is not Phase.PICK_PLAYLIST:
            return
        body = self._fresh_content("Pick a playlist", _BG_NEUTRAL)
        if error:
            self._show_error(error)
            retry = StyledButton(text="Retry", variant="primary", size_hint_y=None, height=64)
            retry.bind(on_release=lambda *_: self._render_pick_playlist())
            body.add_widget(retry)
            return
        if not playlists:
            body.add_widget(Label(text="No playlists found.", font_size="20sp", color=theme.TEXT_MUTED))
            return
        scroll = ScrollView()
        column = BoxLayout(orientation="vertical", size_hint_y=None, spacing=8, padding=(0, 4))
        column.bind(minimum_height=column.setter("height"))
        for playlist in playlists:
            button = StyledButton(
                text=f"{playlist.name}  ({playlist.track_count})",
                variant="secondary",
                size_hint_y=None,
                height=64,
            )
            button.bind(on_release=lambda _b, pid=playlist.playlist_id: self._choose_playlist(pid))
            column.add_widget(button)
        scroll.add_widget(column)
        body.add_widget(scroll)

    def _choose_playlist(self, playlist_id: str) -> None:
        self._fresh_content("Loading tracks...", _BG_NEUTRAL)
        threading.Thread(target=self._load_tracks, args=(playlist_id,), daemon=True).start()

    def _load_tracks(self, playlist_id: str) -> None:
        try:
            tracks = self._service.get_playlist_tracks(playlist_id)
            error = None
        except SpotifyError as exc:
            tracks, error = [], str(exc)
        except Exception:
            logger.exception("Failed to load tracks")
            tracks, error = [], "Could not load tracks; check Spotify and retry."
        Clock.schedule_once(lambda _dt: self._apply_tracks(tracks, error), 0)

    def _apply_tracks(self, tracks: list[TrackInfo], error: str | None) -> None:
        if self._session is None or self._session.phase is not Phase.PICK_PLAYLIST:
            return
        if error or not tracks:
            self._show_error(error or "That playlist has no playable tracks. Pick another.")
            self._render_pick_playlist()
            return
        if self._session.set_playlist(tracks):
            self._clear_error()
            self._render()

    def _render_playing(self) -> None:
        session = self._session
        body = self._fresh_content(f"Round {session.round_number}", _BG_PLAYING)
        body.add_widget(Label(text="Listen... buzz when you know it!", font_size="28sp", color=theme.TEXT))
        body.add_widget(self._scoreboard())

    def _enter_answering(self) -> None:
        config = self._context.settings.config.spotify_buzzer
        self._answer_deadline = time.monotonic() + config.flash_timer_seconds
        self._render_answering()
        self._countdown_event = Clock.schedule_interval(self._tick_answer, 0.05)

    def _render_answering(self) -> None:
        session = self._session
        answerer = session.answering_player if session else None
        name = answerer.display_name if answerer else "Player"
        body = self._fresh_content(f"{name}, your answer!", _BG_FLASH_A)
        self._countdown_label = Label(text="", font_size="72sp", bold=True, color=theme.TEXT)
        body.add_widget(self._countdown_label)
        reveal = StyledButton(text="Reveal answer", variant="primary", size_hint_y=None, height=72)
        reveal.bind(on_release=lambda *_: self._reveal_now())
        body.add_widget(reveal)

    def _tick_answer(self, _dt: float) -> None:
        if self._answer_deadline is None or self._session is None:
            return
        remaining = self._answer_deadline - time.monotonic()
        if remaining <= 0:
            self._cancel_countdown()
            outcome = self._session.timer_expired()
            if outcome is None:  # soft cutoff: now in REVEAL
                self._render()
            else:  # hard cutoff: round resumed/ended
                self._after_outcome(outcome)
            return
        if self._countdown_label is not None:
            self._countdown_label.text = f"{remaining:0.1f}s"
        self._set_bg(_BG_FLASH_A if int(remaining * 2.5) % 2 == 0 else _BG_FLASH_B)

    def _reveal_now(self) -> None:
        self._cancel_countdown()
        if self._session and self._session.reveal_now():
            self._render()

    def _render_reveal(self) -> None:
        session = self._session
        track = session.current_track if session else None
        body = self._fresh_content("Reveal", _BG_DONE)
        if track is None:
            return
        body.add_widget(
            Label(
                text=f"{track.artist} - {track.title}\n{track.year if track.year is not None else 'year unknown'}",
                font_size="30sp",
                color=theme.TEXT,
            )
        )
        at_box, at_check = self._checkbox_row("Artist + Title correct")
        exact_box, exact_check = self._checkbox_row("Year exact")
        close_box, close_check = self._checkbox_row("Year within +/- 1")
        body.add_widget(at_box)
        body.add_widget(exact_box)
        body.add_widget(close_box)

        year_known = track.year is not None
        # Year points only count alongside a correct artist+title.
        for check in (exact_check, close_check):
            check.disabled = True

        def _sync_year_enabled(*_a) -> None:
            enabled = at_check.active and year_known
            for check in (exact_check, close_check):
                check.disabled = not enabled
                if not enabled:
                    check.active = False

        at_check.bind(active=_sync_year_enabled)
        # Exact and close are mutually exclusive; exact wins.
        exact_check.bind(active=lambda _c, v: v and setattr(close_check, "active", False))
        close_check.bind(active=lambda _c, v: v and setattr(exact_check, "active", False))

        confirm = StyledButton(text="Confirm", variant="success", size_hint_y=None, height=72)
        confirm.bind(
            on_release=lambda *_: self._confirm_score(
                artist_title=at_check.active,
                year_exact=exact_check.active,
                year_close=close_check.active,
            )
        )
        body.add_widget(confirm)

    @staticmethod
    def _checkbox_row(label: str) -> tuple[BoxLayout, CheckBox]:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=56, spacing=12)
        check = CheckBox(size_hint_x=None, width=56)
        row.add_widget(check)
        row.add_widget(Label(text=label, font_size="22sp", color=theme.TEXT, halign="left", valign="middle"))
        return row, check

    def _confirm_score(self, *, artist_title: bool, year_exact: bool, year_close: bool) -> None:
        if self._session is None:
            return
        marks = RevealMarks(artist_title_correct=artist_title, year_exact=year_exact, year_close=year_close)
        self._after_outcome(self._session.score_answer(marks))

    def _after_outcome(self, outcome) -> None:
        if outcome.stealing_resumed:
            self._show_error("Wrong - others can steal!", danger=False)
        self._render()

    def _render_between_rounds(self) -> None:
        body = self._fresh_content("Round over", _BG_DONE)
        body.add_widget(self._scoreboard())
        nxt = StyledButton(text="Next round", variant="primary", size_hint_y=None, height=72)
        nxt.bind(on_release=lambda *_: self._next_round())
        body.add_widget(nxt)

    def _next_round(self) -> None:
        if self._session and self._session.next_round():
            self._clear_error()
            self._render()

    def _render_game_over(self) -> None:
        session = self._session
        winners = session.winners() if session else []
        body = self._fresh_content("Game over", _BG_DONE)
        if len(winners) == 1:
            headline = f"Winner: {winners[0].display_name} ({winners[0].score})"
        elif winners:
            names = ", ".join(w.display_name for w in winners)
            headline = f"It's a tie! {names} ({winners[0].score})"
        else:
            headline = "No players"
        body.add_widget(Label(text=headline, font_size="30sp", bold=True, color=theme.SUCCESS))
        body.add_widget(self._scoreboard())

    # -- shared widgets -----------------------------------------------------
    def _scoreboard(self) -> Panel:
        panel = Panel(orientation="vertical", bg=theme.SURFACE, radius=12, padding=12, spacing=6)
        for player in self._session.players() if self._session else []:
            panel.add_widget(Label(text=f"{player.display_name}: {player.score}", font_size="24sp", color=theme.TEXT))
        return panel

    # -- helpers ------------------------------------------------------------
    def _cancel_countdown(self) -> None:
        if self._countdown_event is not None:
            self._countdown_event.cancel()
            self._countdown_event = None
        self._answer_deadline = None
        self._countdown_label = None

    def _set_bg(self, rgba) -> None:
        self._bg_color.rgba = rgba

    def _sync_bg(self, *_args) -> None:
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _show_error(self, message: str, *, danger: bool = True) -> None:
        self._banner.text = message
        self._banner.color = theme.DANGER if danger else theme.TEXT_MUTED
        self._banner.height = 32

    def _clear_error(self) -> None:
        self._banner.text = ""
        self._banner.height = 0
