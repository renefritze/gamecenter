"""Tests for the pure reaction-round state machine and scoring."""

from __future__ import annotations

import random

import pytest

from gamecenter.config.models import (
    POLICY_DISQUALIFY,
    POLICY_PENALTY,
    PlayerSlot,
    ReactionConfig,
)
from gamecenter.games.reaction.logic import Phase, ReactionRound, resolve_player_id


def _round(player_ids, **overrides):
    config = ReactionConfig(min_delay=2.0, max_delay=2.0, **overrides)
    return ReactionRound(player_ids, config, rng=random.Random(0))


def test_arm_returns_go_time_and_enters_wait():
    rnd = _round([0])
    go_at = rnd.arm(now=100.0)
    assert go_at == pytest.approx(102.0)  # fixed delay range
    assert rnd.phase is Phase.WAIT


def test_normal_ranking_orders_by_reaction_time():
    rnd = _round([0, 1, 2])
    rnd.arm(now=0.0)
    rnd.on_go(now=10.0)
    rnd.on_buzz(1, now=10.20)  # 200 ms
    rnd.on_buzz(0, now=10.15)  # 150 ms
    rnd.on_buzz(2, now=10.30)  # 300 ms
    results = rnd.finish()
    assert [r.player_id for r in results] == [0, 1, 2]
    assert [r.rank for r in results] == [1, 2, 3]
    assert round(results[0].reaction_ms) == 150


def test_false_start_disqualifies_under_default_policy():
    rnd = _round([0, 1])
    rnd.arm(now=0.0)
    rnd.on_buzz(0, now=1.0)  # pressed during WAIT -> false start
    rnd.on_go(now=10.0)
    rnd.on_buzz(0, now=10.1)  # ignored: already disqualified
    rnd.on_buzz(1, now=10.2)
    results = rnd.finish()
    winner = next(r for r in results if r.player_id == 1)
    loser = next(r for r in results if r.player_id == 0)
    assert winner.rank == 1
    assert loser.false_start is True
    assert loser.reaction_ms is None
    assert loser.rank is None


def test_false_start_penalty_policy_adds_penalty():
    rnd = _round([0], false_start_policy=POLICY_PENALTY, penalty_ms=500.0)
    rnd.arm(now=0.0)
    rnd.on_buzz(0, now=1.0)  # false start
    rnd.on_go(now=10.0)
    rnd.on_buzz(0, now=10.1)  # 100 ms + 500 ms penalty
    results = rnd.finish()
    assert round(results[0].reaction_ms) == 600
    assert results[0].false_start is True


def test_double_buzz_keeps_first_time():
    rnd = _round([0])
    rnd.arm(now=0.0)
    rnd.on_go(now=10.0)
    rnd.on_buzz(0, now=10.1)
    rnd.on_buzz(0, now=10.9)
    results = rnd.finish()
    assert round(results[0].reaction_ms) == 100


def test_no_buzz_player_ranks_last_without_rank():
    rnd = _round([0, 1])
    rnd.arm(now=0.0)
    rnd.on_go(now=10.0)
    rnd.on_buzz(0, now=10.1)
    results = rnd.finish()
    assert results[0].player_id == 0
    assert results[1].player_id == 1
    assert results[1].reaction_ms is None
    assert results[1].rank is None


def test_all_in_true_once_everyone_settled_disqualify():
    rnd = _round([0, 1], false_start_policy=POLICY_DISQUALIFY)
    rnd.arm(now=0.0)
    assert rnd.all_in is False
    rnd.on_buzz(0, now=1.0)  # false start settles player 0
    rnd.on_go(now=10.0)
    assert rnd.all_in is False
    rnd.on_buzz(1, now=10.1)
    assert rnd.all_in is True


def test_buzz_ignored_before_arm_and_after_finish():
    rnd = _round([0])
    rnd.on_buzz(0, now=1.0)  # IDLE: ignored
    rnd.arm(now=0.0)
    rnd.on_go(now=10.0)
    rnd.finish()
    rnd.on_buzz(0, now=11.0)  # FINISHED: ignored
    results = rnd.results()
    assert results[0].reaction_ms is None


def test_resolve_player_prefers_explicit_mapping():
    players = [
        PlayerSlot(player_id=0, name="A", device_id="hid", buzzer_index=3),
        PlayerSlot(player_id=1, name="B"),
    ]
    assert resolve_player_id(players, "hid", 3) == 0


def test_resolve_player_positional_fallback():
    players = [PlayerSlot(player_id=0, name="A"), PlayerSlot(player_id=1, name="B")]
    assert resolve_player_id(players, "kbd", 1) == 1
    assert resolve_player_id(players, "kbd", 9) is None
