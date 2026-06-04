"""Pure state machine and scoring for the Spotify Buzzer game.

No Kivy, no ``spotipy``, no wall clock: randomness is injected (track choice and
the random start position) and the flash-timer countdown is owned by the widget,
which simply calls :meth:`BuzzerSession.timer_expired`. Every transition and the
scoring - including steals, lockouts and the win condition - is therefore
deterministically testable headless. The widget layer (``widget.py``) drives
this with a Kivy ``Clock`` and a real Spotify-backed ``PlaybackController``.

Flow::

    JOIN -> PICK_PLAYLIST -> PLAYING -> ANSWERING -> REVEAL -+-> BETWEEN_ROUNDS
                               ^                              |       |
                               +------ (steal: resume) -------+       v
                                                                  GAME_OVER
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from gamecenter.config.models import (
    POSITION_AFTER_30S,
    POSITION_RANDOM,
    WIN_TARGET,
)

if TYPE_CHECKING:
    from gamecenter.config.models import PlayerSlot, SpotifyBuzzerConfig
    from gamecenter.services.spotify_protocol import PlaybackController, TrackInfo

# Fixed offset for the "after 30s" start position.
_AFTER_30S_MS = 30_000
# Keep some music after a random start so a buzz still has something to hear.
_RANDOM_TAIL_MS = 5_000


class Phase(str, Enum):
    """Lifecycle phase of a Spotify Buzzer session."""

    JOIN = "join"  # collecting distinct buzzers as players
    PICK_PLAYLIST = "pick_playlist"  # host chooses a playlist
    PLAYING = "playing"  # a track plays; any non-locked player may buzz
    ANSWERING = "answering"  # a player buzzed; playback paused; flash countdown
    REVEAL = "reveal"  # host ticks artist/title/year checkboxes
    BETWEEN_ROUNDS = "between_rounds"  # round scored; awaiting "next round"
    GAME_OVER = "game_over"


@dataclass(slots=True)
class BuzzerPlayer:
    """A player and the physical buzzer that joined them."""

    player_id: int
    device_id: str
    buzzer_index: int
    display_name: str
    score: int = 0

    @property
    def key(self) -> tuple[str, int]:
        """The ``(device_id, buzzer_index)`` identifying this player's buzzer."""
        return (self.device_id, self.buzzer_index)


@dataclass(slots=True)
class RevealMarks:
    """The host's checkbox judgement for the answering player.

    Year points only count when ``artist_title_correct`` is also set; the widget
    enforces this by disabling the year checkboxes until artist+title is ticked.
    """

    artist_title_correct: bool = False
    year_exact: bool = False
    year_close: bool = False


@dataclass(slots=True)
class RoundOutcome:
    """What :meth:`BuzzerSession.score_answer` decided."""

    awarded_points: int
    correct: bool
    stealing_resumed: bool
    round_ended: bool
    game_over: bool


def resolve_display_name(known_players: list[PlayerSlot], device_id: str, buzzer_index: int, fallback: str) -> str:
    """Return a configured player's name for this buzzer, else ``fallback``."""
    for slot in known_players:
        if slot.key == (device_id, buzzer_index):
            return slot.name
    return fallback


class BuzzerSession:
    """Drives one game of Spotify Buzzer across many rounds."""

    def __init__(
        self,
        config: SpotifyBuzzerConfig,
        playback: PlaybackController,
        rng: random.Random | None = None,
        known_players: list[PlayerSlot] | None = None,
    ) -> None:
        """Create a session bound to ``config`` and a ``playback`` controller."""
        self._config = config
        self._playback = playback
        self._rng = rng or random.Random()
        self._known_players = known_players or []
        self._phase = Phase.JOIN
        # Insertion order is join order, so dict preserves P1..Pn ordering.
        self._players: dict[tuple[str, int], BuzzerPlayer] = {}
        self._next_player_id = 1
        self._playlist_tracks: list[TrackInfo] = []
        self._current: TrackInfo | None = None
        self._answering_id: int | None = None
        self._locked_out: set[int] = set()
        self._round_number = 0

    # -- accessors ----------------------------------------------------------
    @property
    def phase(self) -> Phase:
        """Current phase of the session."""
        return self._phase

    @property
    def current_track(self) -> TrackInfo | None:
        """The track for the current round (do not show before REVEAL)."""
        return self._current

    @property
    def answering_player(self) -> BuzzerPlayer | None:
        """The player currently answering, if any."""
        if self._answering_id is None:
            return None
        return self._player_by_id(self._answering_id)

    @property
    def round_number(self) -> int:
        """1-based index of the current round (0 before the first round)."""
        return self._round_number

    @property
    def is_over(self) -> bool:
        """Whether the game has ended."""
        return self._phase is Phase.GAME_OVER

    def players(self) -> list[BuzzerPlayer]:
        """All joined players, in join order."""
        return list(self._players.values())

    def scores(self) -> dict[int, int]:
        """Map of player id to cumulative score."""
        return {p.player_id: p.score for p in self._players.values()}

    def player_for(self, device_id: str, buzzer_index: int) -> BuzzerPlayer | None:
        """Return the player joined on this buzzer, if any."""
        return self._players.get((device_id, buzzer_index))

    def winners(self) -> list[BuzzerPlayer]:
        """Players sharing the top score (empty if no players)."""
        if not self._players:
            return []
        top = max(p.score for p in self._players.values())
        return [p for p in self._players.values() if p.score == top]

    # -- JOIN ---------------------------------------------------------------
    def join_buzz(self, device_id: str, buzzer_index: int) -> BuzzerPlayer | None:
        """Register the buzzer as a player during JOIN; idempotent on repeats."""
        if self._phase is not Phase.JOIN:
            return None
        key = (device_id, buzzer_index)
        existing = self._players.get(key)
        if existing is not None:
            return existing
        name = resolve_display_name(self._known_players, device_id, buzzer_index, f"P{self._next_player_id}")
        player = BuzzerPlayer(
            player_id=self._next_player_id,
            device_id=device_id,
            buzzer_index=buzzer_index,
            display_name=name,
        )
        self._players[key] = player
        self._next_player_id += 1
        return player

    def finish_join(self) -> bool:
        """Leave JOIN for PICK_PLAYLIST; requires at least one player."""
        if self._phase is not Phase.JOIN or not self._players:
            return False
        self._phase = Phase.PICK_PLAYLIST
        return True

    # -- PICK_PLAYLIST ------------------------------------------------------
    def set_playlist(self, tracks: list[TrackInfo]) -> bool:
        """Adopt ``tracks`` and start the first round; reject an empty list."""
        if self._phase is not Phase.PICK_PLAYLIST or not tracks:
            return False
        self._playlist_tracks = list(tracks)
        self._start_round()
        return True

    # -- round lifecycle ----------------------------------------------------
    def _start_round(self) -> TrackInfo:
        self._locked_out.clear()
        self._answering_id = None
        self._current = self._rng.choice(self._playlist_tracks)
        self._round_number += 1
        self._playback.play(self._current.uri, self._position_ms(self._current))
        self._phase = Phase.PLAYING
        return self._current

    def _position_ms(self, track: TrackInfo) -> int:
        mode = self._config.position_mode
        if mode == POSITION_AFTER_30S:
            # Never seek past the end; keep a little music to hear.
            return min(_AFTER_30S_MS, max(0, track.duration_ms - 1_000))
        if mode == POSITION_RANDOM:
            upper = max(1, track.duration_ms - _RANDOM_TAIL_MS)
            return self._rng.randrange(0, upper)
        return 0  # POSITION_START (and any unknown value)

    def buzz(self, player_id: int) -> bool:
        """Accept a buzz during PLAYING; pause and enter ANSWERING on success."""
        if self._phase is not Phase.PLAYING or self._answering_id is not None:
            return False
        if player_id in self._locked_out or self._player_by_id(player_id) is None:
            return False
        self._answering_id = player_id
        self._playback.pause()
        self._phase = Phase.ANSWERING
        return True

    def reveal_now(self) -> bool:
        """Host reveals the answer (cancels the countdown); enter REVEAL."""
        if self._phase is not Phase.ANSWERING:
            return False
        self._phase = Phase.REVEAL
        return True

    def timer_expired(self) -> RoundOutcome | None:
        """Handle the flash countdown elapsing.

        Soft (default): reveal so the host can still award points. Hard cutoff:
        treat as a wrong answer immediately (lock out and steal/end).
        """
        if self._phase is not Phase.ANSWERING:
            return None
        if self._config.timer_hard_cutoff:
            return self.score_answer(RevealMarks())
        self._phase = Phase.REVEAL
        return None

    def score_answer(self, marks: RevealMarks) -> RoundOutcome:
        """Award points for the answering player and decide steal vs end.

        Reached identically by the original buzzer and every stealer. A correct
        answer (artist+title) ends the round; a wrong one locks the answerer out
        and resumes the song for any remaining player, or ends the round if all
        are now locked out.
        """
        answerer = self.answering_player
        if self._phase not in (Phase.REVEAL, Phase.ANSWERING) or answerer is None:
            return RoundOutcome(0, correct=False, stealing_resumed=False, round_ended=False, game_over=False)

        points = self._points_for(marks)
        answerer.score += points
        correct = marks.artist_title_correct

        if correct:
            self._answering_id = None
            return self._end_round(awarded=points, correct=True)

        # Wrong answer: lock the answerer out of the rest of this song.
        self._locked_out.add(answerer.player_id)
        self._answering_id = None
        if self._has_eligible_player():
            self._playback.resume()
            self._phase = Phase.PLAYING
            return RoundOutcome(points, correct=False, stealing_resumed=True, round_ended=False, game_over=False)
        return self._end_round(awarded=points, correct=False)

    def next_round(self) -> bool:
        """Start the next round from BETWEEN_ROUNDS."""
        if self._phase is not Phase.BETWEEN_ROUNDS:
            return False
        self._start_round()
        return True

    # -- internals ----------------------------------------------------------
    def _points_for(self, marks: RevealMarks) -> int:
        if not marks.artist_title_correct:
            return 0  # year points only count alongside a correct artist+title
        points = self._config.points_artist_title
        if marks.year_exact:
            points += self._config.points_year_exact
        elif marks.year_close:
            points += self._config.points_year_close
        return points

    def _end_round(self, *, awarded: int, correct: bool) -> RoundOutcome:
        self._playback.pause()
        game_over = self._config.win_mode == WIN_TARGET and any(
            p.score >= self._config.target_points for p in self._players.values()
        )
        self._phase = Phase.GAME_OVER if game_over else Phase.BETWEEN_ROUNDS
        return RoundOutcome(
            awarded,
            correct=correct,
            stealing_resumed=False,
            round_ended=True,
            game_over=game_over,
        )

    def _has_eligible_player(self) -> bool:
        return any(p.player_id not in self._locked_out for p in self._players.values())

    def _player_by_id(self, player_id: int) -> BuzzerPlayer | None:
        for player in self._players.values():
            if player.player_id == player_id:
                return player
        return None
