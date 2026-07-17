"""Tests for the pure Trivia Quiz state machine and scoring."""

from __future__ import annotations

import random

from gamecenter.config.models import PlayerSlot, QuizConfig
from gamecenter.games.quiz.logic import Phase, QuizSession
from gamecenter.games.quiz.sources import QuizQuestion


def _question(text="Q?", answer="A"):
    return QuizQuestion(text=text, answer=answer)


def _questions(n=3):
    return [_question(text=f"Q{i}?", answer=f"A{i}") for i in range(n)]


def _session(config=None, seed=0):
    return QuizSession(config or QuizConfig(), rng=random.Random(seed))


def _started(config=None, n_players=2, n_questions=3, seed=0):
    session = _session(config, seed)
    for i in range(n_players):
        session.join_buzz("kbd", i)
    session.finish_join()
    session.set_questions(_questions(n_questions))
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
    assert session.phase is Phase.PICK_SET


def test_join_uses_configured_name_when_buzzer_matches():
    known = [PlayerSlot(player_id=0, name="Ann", device_id="kbd", buzzer_index=0)]
    session = QuizSession(QuizConfig(), known_players=known)
    player = session.join_buzz("kbd", 0)
    assert player.display_name == "Ann"


# -- PICK_SET ----------------------------------------------------------------
def test_empty_question_list_is_rejected():
    session = _session()
    session.join_buzz("kbd", 0)
    session.finish_join()
    assert session.set_questions([]) is False
    assert session.phase is Phase.PICK_SET


def test_set_questions_starts_first_question():
    session = _started(n_questions=3)
    assert session.phase is Phase.QUESTION
    assert session.question_number == 1
    assert session.total_questions == 3
    assert session.current_question is not None


def test_set_questions_caps_at_questions_per_game():
    session = _started(QuizConfig(questions_per_game=2), n_questions=5)
    assert session.total_questions == 2


def test_set_questions_shuffles_deterministically():
    a = _started(seed=1, n_questions=5)
    b = _started(seed=1, n_questions=5)
    assert [q.text for q in a._questions] == [q.text for q in b._questions]


# -- buzzing and the answer countdown ---------------------------------------
def test_buzz_enters_answering():
    session = _started()
    assert session.buzz(1) is True
    assert session.phase is Phase.ANSWERING
    assert session.answering_player.player_id == 1


def test_second_buzz_rejected_while_answering():
    session = _started()
    session.buzz(1)
    assert session.buzz(2) is False
    assert session.answering_player.player_id == 1


def test_buzz_rejected_for_unknown_player():
    session = _started()
    assert session.buzz(99) is False
    assert session.phase is Phase.QUESTION


def test_timeout_reveals_the_answer():
    session = _started()
    session.buzz(1)
    assert session.timeout_expired() is True
    assert session.phase is Phase.REVEAL


def test_reveal_now_matches_timeout():
    session = _started()
    session.buzz(1)
    assert session.reveal_now() is True
    assert session.phase is Phase.REVEAL


def test_timeout_ignored_outside_answering():
    session = _started()
    assert session.timeout_expired() is False
    assert session.phase is Phase.QUESTION


# -- judging and scoring -----------------------------------------------------
def test_correct_answer_scores_points():
    session = _started(QuizConfig(points_correct=2))
    session.buzz(1)
    session.timeout_expired()
    outcome = session.judge(correct=True)
    assert outcome.awarded_points == 2
    assert outcome.correct is True
    assert session.scores()[1] == 2
    assert session.phase is Phase.BETWEEN_ROUNDS


def test_wrong_answer_applies_penalty():
    session = _started(QuizConfig(points_wrong=-1))
    session.buzz(1)
    session.timeout_expired()
    outcome = session.judge(correct=False)
    assert outcome.awarded_points == -1
    assert outcome.correct is False
    assert session.scores()[1] == -1


def test_wrong_answer_default_scores_nothing():
    session = _started()
    session.buzz(1)
    session.timeout_expired()
    outcome = session.judge(correct=False)
    assert outcome.awarded_points == 0
    assert session.scores()[1] == 0


def test_judge_rejected_outside_reveal():
    session = _started()
    assert session.judge(correct=True) is None


# -- skipping ----------------------------------------------------------------
def test_skip_reveals_without_answerer():
    session = _started()
    assert session.skip_question() is True
    assert session.phase is Phase.REVEAL
    assert session.answering_player is None
    outcome = session.judge(correct=False)
    assert outcome.awarded_points == 0
    assert session.scores() == {1: 0, 2: 0}


# -- game progression --------------------------------------------------------
def test_next_question_advances():
    session = _started(n_questions=3)
    first = session.current_question
    session.buzz(1)
    session.timeout_expired()
    session.judge(correct=True)
    assert session.next_question() is True
    assert session.phase is Phase.QUESTION
    assert session.question_number == 2
    assert session.current_question is not first


def test_last_question_ends_the_game():
    session = _started(n_questions=1)
    session.buzz(1)
    session.timeout_expired()
    outcome = session.judge(correct=True)
    assert outcome.game_over is True
    assert session.is_over is True
    assert session.next_question() is False


def test_winners_exposes_ties():
    session = _started(n_questions=3)
    session.buzz(1)
    session.timeout_expired()
    session.judge(correct=True)
    session.next_question()
    session.buzz(2)
    session.timeout_expired()
    session.judge(correct=True)
    winners = session.winners()
    assert {w.player_id for w in winners} == {1, 2}


def test_single_winner():
    session = _started(n_questions=1)
    session.buzz(2)
    session.timeout_expired()
    session.judge(correct=True)
    winners = session.winners()
    assert [w.player_id for w in winners] == [2]
