"""Pure state machine and scoring for the Trivia Quiz game.

No Kivy and no wall clock: the answer countdown is owned by the widget, which
calls :meth:`QuizSession.timeout_expired` when the configured
``answer_timeout_seconds`` elapse. Question order randomness is injected, so
every transition and the scoring are deterministically testable headless.

Flow::

    JOIN -> PICK_SET -> QUESTION -> ANSWERING -> REVEAL -+-> BETWEEN_ROUNDS
              (host      ^  (buzz)    (countdown) (yes/no)|        |
               picks a   |                                v        v
               source)   +--------- (next question) --- GAME_OVER (last one)

A buzz freezes the question and starts the countdown; when it expires (or the
host reveals early) the answer is shown and the host judges correct yes/no.
Skipping an unanswered question also goes through REVEAL, with no answerer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gamecenter.config.models import PlayerSlot, QuizConfig
    from gamecenter.games.quiz.sources import QuizQuestion


class Phase(str, Enum):
    """Lifecycle phase of a Trivia Quiz session."""

    JOIN = "join"  # collecting distinct buzzers as players
    PICK_SET = "pick_set"  # host chooses a question source/set
    QUESTION = "question"  # a question shows; any player may buzz
    ANSWERING = "answering"  # a player buzzed; countdown until the reveal
    REVEAL = "reveal"  # answer shown; host judges correct yes/no
    BETWEEN_ROUNDS = "between_rounds"  # question scored; awaiting "next"
    GAME_OVER = "game_over"


@dataclass(slots=True)
class QuizPlayer:
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
class JudgeOutcome:
    """What :meth:`QuizSession.judge` decided."""

    awarded_points: int
    correct: bool
    game_over: bool


def _resolve_display_name(known_players: list[PlayerSlot], device_id: str, buzzer_index: int, fallback: str) -> str:
    for slot in known_players:
        if slot.key == (device_id, buzzer_index):
            return slot.name
    return fallback


class QuizSession:
    """Drives one quiz across a fixed number of questions."""

    def __init__(
        self,
        config: QuizConfig,
        rng: random.Random | None = None,
        known_players: list[PlayerSlot] | None = None,
    ) -> None:
        """Create a session bound to ``config``."""
        self._config = config
        self._rng = rng or random.Random()
        self._known_players = known_players or []
        self._phase = Phase.JOIN
        # Insertion order is join order, so dict preserves P1..Pn ordering.
        self._players: dict[tuple[str, int], QuizPlayer] = {}
        self._next_player_id = 1
        self._questions: list[QuizQuestion] = []
        self._index = 0
        self._answering_id: int | None = None

    # -- accessors ----------------------------------------------------------
    @property
    def phase(self) -> Phase:
        """Current phase of the session."""
        return self._phase

    @property
    def current_question(self) -> QuizQuestion | None:
        """The question being played, or ``None`` before the game starts."""
        if not self._questions or self._phase in (Phase.JOIN, Phase.PICK_SET):
            return None
        return self._questions[self._index]

    @property
    def question_number(self) -> int:
        """1-based number of the current question (0 before the game starts)."""
        if self.current_question is None:
            return 0
        return self._index + 1

    @property
    def total_questions(self) -> int:
        """How many questions this game will ask."""
        return len(self._questions)

    @property
    def answering_player(self) -> QuizPlayer | None:
        """The player who buzzed for the current question, if any."""
        if self._answering_id is None:
            return None
        for player in self._players.values():
            if player.player_id == self._answering_id:
                return player
        return None

    @property
    def is_over(self) -> bool:
        """Whether the game has ended."""
        return self._phase is Phase.GAME_OVER

    def players(self) -> list[QuizPlayer]:
        """All joined players, in join order."""
        return list(self._players.values())

    def scores(self) -> dict[int, int]:
        """Map of player id to cumulative score."""
        return {p.player_id: p.score for p in self._players.values()}

    def player_for(self, device_id: str, buzzer_index: int) -> QuizPlayer | None:
        """Return the player joined on this buzzer, if any."""
        return self._players.get((device_id, buzzer_index))

    def winners(self) -> list[QuizPlayer]:
        """Players sharing the top score (empty if no players)."""
        if not self._players:
            return []
        top = max(p.score for p in self._players.values())
        return [p for p in self._players.values() if p.score == top]

    # -- JOIN ---------------------------------------------------------------
    def join_buzz(self, device_id: str, buzzer_index: int) -> QuizPlayer | None:
        """Register the buzzer as a player during JOIN; idempotent on repeats."""
        if self._phase is not Phase.JOIN:
            return None
        key = (device_id, buzzer_index)
        existing = self._players.get(key)
        if existing is not None:
            return existing
        name = _resolve_display_name(self._known_players, device_id, buzzer_index, f"P{self._next_player_id}")
        player = QuizPlayer(
            player_id=self._next_player_id,
            device_id=device_id,
            buzzer_index=buzzer_index,
            display_name=name,
        )
        self._players[key] = player
        self._next_player_id += 1
        return player

    def finish_join(self) -> bool:
        """Leave JOIN for PICK_SET; requires at least one player."""
        if self._phase is not Phase.JOIN or not self._players:
            return False
        self._phase = Phase.PICK_SET
        return True

    # -- PICK_SET -----------------------------------------------------------
    def set_questions(self, questions: list[QuizQuestion]) -> bool:
        """Adopt (a shuffled slice of) ``questions`` and ask the first one."""
        if self._phase is not Phase.PICK_SET or not questions:
            return False
        pool = list(questions)
        self._rng.shuffle(pool)
        self._questions = pool[: max(1, self._config.questions_per_game)]
        self._index = 0
        self._phase = Phase.QUESTION
        return True

    # -- question lifecycle -------------------------------------------------
    def buzz(self, player_id: int) -> bool:
        """Accept the first buzz during QUESTION; starts the answer countdown."""
        if self._phase is not Phase.QUESTION or self._answering_id is not None:
            return False
        if not any(p.player_id == player_id for p in self._players.values()):
            return False
        self._answering_id = player_id
        self._phase = Phase.ANSWERING
        return True

    def timeout_expired(self) -> bool:
        """Show the answer (REVEAL) once the configured answer timeout elapses."""
        if self._phase is not Phase.ANSWERING:
            return False
        self._phase = Phase.REVEAL
        return True

    def reveal_now(self) -> bool:
        """Host shows the answer before the countdown ends; enter REVEAL."""
        return self.timeout_expired()

    def skip_question(self) -> bool:
        """Nobody buzzed: reveal the answer with no player to judge."""
        if self._phase is not Phase.QUESTION:
            return False
        self._answering_id = None
        self._phase = Phase.REVEAL
        return True

    def judge(self, *, correct: bool) -> JudgeOutcome | None:
        """Host's yes/no verdict for the answering player; scores and advances.

        With no answerer (a skipped question) nothing is scored, the game just
        moves on. The last question ends the game instead of BETWEEN_ROUNDS.
        """
        if self._phase is not Phase.REVEAL:
            return None
        answerer = self.answering_player
        points = 0
        if answerer is not None:
            points = self._config.points_correct if correct else self._config.points_wrong
            answerer.score += points
        self._answering_id = None
        game_over = self._index + 1 >= len(self._questions)
        self._phase = Phase.GAME_OVER if game_over else Phase.BETWEEN_ROUNDS
        return JudgeOutcome(awarded_points=points, correct=correct and answerer is not None, game_over=game_over)

    def next_question(self) -> bool:
        """Advance to the next question from BETWEEN_ROUNDS."""
        if self._phase is not Phase.BETWEEN_ROUNDS:
            return False
        self._index += 1
        self._phase = Phase.QUESTION
        return True
