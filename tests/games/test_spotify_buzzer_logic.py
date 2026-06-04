"""Tests for the pure Spotify Buzzer state machine and scoring."""

from __future__ import annotations

import random

from gamecenter.config.models import (
    POSITION_AFTER_30S,
    POSITION_RANDOM,
    POSITION_START,
    WIN_TARGET,
    SpotifyBuzzerConfig,
)
from gamecenter.games.spotify_buzzer.logic import (
    BuzzerSession,
    Phase,
    RevealMarks,
)
from gamecenter.services.spotify_protocol import TrackInfo


class FakePlayback:
    """Records playback calls so transitions can be asserted."""

    def __init__(self):
        self.calls = []

    def play(self, uri, position_ms):
        self.calls.append(("play", uri, position_ms))

    def resume(self):
        self.calls.append(("resume",))

    def pause(self):
        self.calls.append(("pause",))


def _track(uri="spotify:track:1", artist="A", title="T", year=2000, duration_ms=200_000):
    return TrackInfo(uri=uri, artist=artist, title=title, year=year, duration_ms=duration_ms)


def _session(config=None, playback=None, seed=0):
    return BuzzerSession(
        config or SpotifyBuzzerConfig(),
        playback or FakePlayback(),
        rng=random.Random(seed),
    )


def _joined(config=None, playback=None, n=2, seed=0):
    session = _session(config, playback, seed)
    for i in range(n):
        session.join_buzz("kbd", i)
    session.finish_join()
    return session


# -- JOIN --------------------------------------------------------------------
def test_join_creates_sequential_players():
    session = _session()
    p1 = session.join_buzz("kbd", 0)
    p2 = session.join_buzz("kbd", 1)
    assert [p.player_id for p in (p1, p2)] == [1, 2]
    assert [p.display_name for p in session.players()] == ["P1", "P2"]


def test_join_is_idempotent_per_buzzer():
    session = _session()
    first = session.join_buzz("kbd", 0)
    again = session.join_buzz("kbd", 0)
    assert first is again
    assert len(session.players()) == 1


def test_finish_join_requires_a_player():
    session = _session()
    assert session.finish_join() is False
    assert session.phase is Phase.JOIN
    session.join_buzz("kbd", 0)
    assert session.finish_join() is True
    assert session.phase is Phase.PICK_PLAYLIST


def test_join_uses_configured_name_when_buzzer_matches():
    from gamecenter.config.models import PlayerSlot

    known = [PlayerSlot(player_id=0, name="Ann", device_id="kbd", buzzer_index=0)]
    session = BuzzerSession(SpotifyBuzzerConfig(), FakePlayback(), known_players=known)
    player = session.join_buzz("kbd", 0)
    assert player.display_name == "Ann"


# -- PICK_PLAYLIST -----------------------------------------------------------
def test_empty_playlist_is_rejected():
    session = _joined()
    assert session.set_playlist([]) is False
    assert session.phase is Phase.PICK_PLAYLIST


def test_set_playlist_starts_first_round_and_plays():
    playback = FakePlayback()
    session = _joined(playback=playback)
    assert session.set_playlist([_track()]) is True
    assert session.phase is Phase.PLAYING
    assert session.round_number == 1
    assert playback.calls[0][0] == "play"


# -- start position ----------------------------------------------------------
def test_position_start_is_zero():
    playback = FakePlayback()
    session = _joined(SpotifyBuzzerConfig(position_mode=POSITION_START), playback)
    session.set_playlist([_track(duration_ms=200_000)])
    assert playback.calls[0] == ("play", "spotify:track:1", 0)


def test_position_after_30s_clamped_to_track():
    playback = FakePlayback()
    session = _joined(SpotifyBuzzerConfig(position_mode=POSITION_AFTER_30S), playback)
    session.set_playlist([_track(duration_ms=200_000)])
    assert playback.calls[0] == ("play", "spotify:track:1", 30_000)


def test_position_random_is_within_bounds_and_deterministic():
    playback = FakePlayback()
    session = _joined(SpotifyBuzzerConfig(position_mode=POSITION_RANDOM), playback, seed=0)
    session.set_playlist([_track(duration_ms=200_000)])
    pos = playback.calls[0][2]
    assert 0 <= pos < 195_000


# -- buzzing -----------------------------------------------------------------
def test_buzz_pauses_and_enters_answering():
    playback = FakePlayback()
    session = _joined(playback=playback)
    session.set_playlist([_track()])
    assert session.buzz(1) is True
    assert session.phase is Phase.ANSWERING
    assert ("pause",) in playback.calls
    assert session.answering_player.player_id == 1


def test_second_buzz_rejected_while_answering():
    session = _joined()
    session.set_playlist([_track()])
    session.buzz(1)
    assert session.buzz(2) is False


def test_buzz_rejected_for_unknown_player():
    session = _joined()
    session.set_playlist([_track()])
    assert session.buzz(99) is False


# -- scoring -----------------------------------------------------------------
def _to_reveal(session, player=1):
    session.buzz(player)
    session.reveal_now()


def test_correct_artist_title_scores_and_ends_round():
    session = _joined()
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=True))
    assert outcome.awarded_points == 1
    assert outcome.correct is True
    assert outcome.round_ended is True
    assert session.scores()[1] == 1
    assert session.phase is Phase.BETWEEN_ROUNDS


def test_year_exact_adds_to_artist_title():
    session = _joined()
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=True, year_exact=True))
    assert outcome.awarded_points == 4  # 1 + 3


def test_year_close_adds_one():
    session = _joined()
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=True, year_close=True))
    assert outcome.awarded_points == 2  # 1 + 1


def test_exact_beats_close_when_both_ticked():
    session = _joined()
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=True, year_exact=True, year_close=True))
    assert outcome.awarded_points == 4  # exact wins, not 1+3+1


def test_year_alone_scores_nothing():
    session = _joined()
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=False, year_exact=True))
    assert outcome.awarded_points == 0
    assert session.scores()[1] == 0


# -- steal -------------------------------------------------------------------
def test_wrong_answer_locks_out_and_resumes_for_steal():
    playback = FakePlayback()
    session = _joined(playback=playback, n=2)
    session.set_playlist([_track()])
    _to_reveal(session, player=1)
    outcome = session.score_answer(RevealMarks(artist_title_correct=False))
    assert outcome.stealing_resumed is True
    assert session.phase is Phase.PLAYING
    assert ("resume",) in playback.calls
    # The original buzzer is locked out; a different player may steal.
    assert session.buzz(1) is False
    assert session.buzz(2) is True


def test_stealer_scores_and_ends_round():
    session = _joined(n=2)
    session.set_playlist([_track()])
    _to_reveal(session, player=1)
    session.score_answer(RevealMarks(artist_title_correct=False))  # P1 wrong, resume
    session.buzz(2)
    session.reveal_now()
    outcome = session.score_answer(RevealMarks(artist_title_correct=True))
    assert outcome.round_ended is True
    assert session.scores() == {1: 0, 2: 1}


def test_all_locked_out_ends_round_without_resume():
    playback = FakePlayback()
    session = _joined(playback=playback, n=1)
    session.set_playlist([_track()])
    _to_reveal(session, player=1)
    outcome = session.score_answer(RevealMarks(artist_title_correct=False))
    assert outcome.stealing_resumed is False
    assert outcome.round_ended is True
    assert session.phase is Phase.BETWEEN_ROUNDS
    assert ("resume",) not in playback.calls


def test_next_round_clears_lockout():
    session = _joined(n=2)
    session.set_playlist([_track(), _track(uri="spotify:track:2")])
    _to_reveal(session, player=1)
    session.score_answer(RevealMarks(artist_title_correct=True))
    assert session.next_round() is True
    assert session.phase is Phase.PLAYING
    # P1 was not locked out into the new round.
    assert session.buzz(1) is True


# -- flash timer -------------------------------------------------------------
def test_timer_expired_soft_reveals():
    session = _joined()
    session.set_playlist([_track()])
    session.buzz(1)
    assert session.timer_expired() is None
    assert session.phase is Phase.REVEAL


def test_timer_expired_hard_cutoff_treats_as_wrong():
    config = SpotifyBuzzerConfig(timer_hard_cutoff=True)
    session = _joined(config=config, n=2)
    session.set_playlist([_track()])
    session.buzz(1)
    outcome = session.timer_expired()
    assert outcome is not None
    assert outcome.correct is False
    assert session.buzz(1) is False  # locked out
    assert session.phase is Phase.PLAYING  # resumed for steal


# -- win condition -----------------------------------------------------------
def test_target_mode_ends_game_when_reached():
    config = SpotifyBuzzerConfig(win_mode=WIN_TARGET, target_points=1)
    session = _joined(config=config)
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=True))
    assert outcome.game_over is True
    assert session.is_over is True


def test_infinite_mode_never_ends():
    session = _joined()
    session.set_playlist([_track()])
    _to_reveal(session)
    outcome = session.score_answer(RevealMarks(artist_title_correct=True))
    assert outcome.game_over is False
    assert session.phase is Phase.BETWEEN_ROUNDS


def test_winners_exposes_ties():
    config = SpotifyBuzzerConfig(win_mode=WIN_TARGET, target_points=99)
    session = _joined(config=config, n=2)
    session.set_playlist([_track(), _track(uri="spotify:track:2")])
    _to_reveal(session, player=1)
    session.score_answer(RevealMarks(artist_title_correct=True))
    session.next_round()
    _to_reveal(session, player=2)
    session.score_answer(RevealMarks(artist_title_correct=True))
    winners = session.winners()
    assert {w.player_id for w in winners} == {1, 2}
