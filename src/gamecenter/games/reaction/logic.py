"""Pure state machine and scoring for the Reaction Test game.

No Kivy, no real clock: timestamps and randomness are injected, so the whole
round - including false starts, ties and ranking - is deterministically
testable headless. The widget layer (``widget.py``) merely drives this with a
Kivy ``Clock`` and real buzzer events.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from gamecenter.config.models import POLICY_PENALTY

if TYPE_CHECKING:
    from gamecenter.config.models import PlayerSlot, ReactionConfig


def resolve_player_id(players: list[PlayerSlot], device_id: str, buzzer_index: int) -> int | None:
    """Map a physical buzzer to a player id.

    Prefers an explicit ``(device_id, buzzer_index)`` mapping from settings;
    falls back to the buzzer index's position in ``players`` so the keyboard
    dev fallback works without any mapping configured.
    """
    for slot in players:
        if slot.key == (device_id, buzzer_index):
            return slot.player_id
    if 0 <= buzzer_index < len(players):
        return players[buzzer_index].player_id
    return None


class Phase(str, Enum):
    """Lifecycle phase of a single reaction round."""

    IDLE = "idle"
    WAIT = "wait"  # armed; pressing now is a false start
    GO = "go"  # the GO signal is shown; press to record a time
    FINISHED = "finished"


@dataclass(slots=True)
class PlayerResult:
    """Per-player outcome within a round."""

    player_id: int
    reaction_ms: float | None = None
    false_start: bool = False
    rank: int | None = None

    @property
    def has_time(self) -> bool:
        """Whether the player recorded a valid (rankable) reaction time."""
        return self.reaction_ms is not None


class ReactionRound:
    """Drives one reaction round and computes the ranking."""

    def __init__(
        self,
        player_ids: list[int],
        config: ReactionConfig,
        rng: random.Random | None = None,
    ) -> None:
        """Create a round for ``player_ids`` using ``config`` and optional ``rng``."""
        self._config = config
        self._rng = rng or random.Random()
        self._phase = Phase.IDLE
        self._go_time: float | None = None
        self._results = {pid: PlayerResult(player_id=pid) for pid in player_ids}

    @property
    def phase(self) -> Phase:
        """Current phase of the round."""
        return self._phase

    def arm(self, now: float) -> float:
        """Arm the round; return the monotonic time at which GO should fire."""
        delay = self._rng.uniform(self._config.min_delay, self._config.max_delay)
        self._phase = Phase.WAIT
        return now + delay

    def on_go(self, now: float) -> None:
        """Fire the GO signal."""
        if self._phase is not Phase.WAIT:
            return
        self._go_time = now
        self._phase = Phase.GO

    def on_buzz(self, player_id: int, now: float) -> None:
        """Record a buzzer press for ``player_id`` at monotonic time ``now``."""
        result = self._results.get(player_id)
        if result is None or self._phase in (Phase.IDLE, Phase.FINISHED):
            return
        penalty_policy = self._config.false_start_policy == POLICY_PENALTY

        if self._phase is Phase.WAIT:
            # Pressed before GO: a false start.
            if not result.false_start:
                result.false_start = True
            return

        # Phase.GO: record the first valid press only.
        if result.reaction_ms is not None or self._go_time is None:
            return
        if result.false_start and not penalty_policy:
            # Disqualified by an earlier false start; ignore the press.
            return
        elapsed_ms = (now - self._go_time) * 1000.0
        if result.false_start and penalty_policy:
            elapsed_ms += self._config.penalty_ms
        result.reaction_ms = max(0.0, elapsed_ms)

    @property
    def all_in(self) -> bool:
        """Whether every player has settled (used to finish the round early)."""
        penalty_policy = self._config.false_start_policy == POLICY_PENALTY
        for result in self._results.values():
            settled = result.has_time or (result.false_start and not penalty_policy)
            if not settled:
                return False
        return True

    def finish(self) -> list[PlayerResult]:
        """Mark the round finished and return the ranked results."""
        self._phase = Phase.FINISHED
        return self.results()

    def results(self) -> list[PlayerResult]:
        """Return results ranked: valid times first (ascending), then the rest.

        Disqualified false starts come before players who never buzzed; only
        valid-timed players receive a numeric ``rank``.
        """
        results = list(self._results.values())

        def sort_key(result: PlayerResult) -> tuple[int, float, int]:
            if result.has_time:
                return (0, result.reaction_ms or 0.0, result.player_id)
            if result.false_start:
                return (1, 0.0, result.player_id)
            return (2, 0.0, result.player_id)

        results.sort(key=sort_key)
        rank = 0
        for result in results:
            if result.has_time:
                rank += 1
                result.rank = rank
            else:
                result.rank = None
        return results
