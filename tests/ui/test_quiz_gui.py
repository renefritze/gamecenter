"""Headless GUI smoke test for the Trivia Quiz widget.

Marked ``gui`` so it is deselected by the default ``-m 'not gui'`` addopts; run
under a virtual display, e.g. ``xvfb-run -a pytest -m gui``. Feeds questions
straight into the session (skipping the threaded fetch) to exercise every
render path plus buzzer handling, the reveal, and yes/no judging.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")

pytestmark = pytest.mark.gui


def _build_widget():
    """Build a QuizWidget on a fresh context, or skip without a display."""
    from gamecenter.config.service import SettingsService
    from gamecenter.core.game_api import GameContext
    from gamecenter.core.registry import ServiceRegistry
    from gamecenter.games.quiz.widget import QuizWidget
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
        return QuizWidget(context)
    except Exception as exc:  # pragma: no cover - environment without a usable window
        pytest.skip(f"No usable Kivy window provider: {exc}")


@pytest.fixture
def widget():
    instance = _build_widget()
    instance.begin()
    yield instance
    instance.shutdown()


def _event(buzzer_index):
    from gamecenter.core.events import ButtonKind, BuzzerEvent

    return BuzzerEvent(device_id="kbd", buzzer_index=buzzer_index, button=ButtonKind.BUZZ, timestamp=0.0, raw=None)


def _questions(n=2):
    from gamecenter.games.quiz.sources import QuizQuestion

    return [QuizQuestion(text=f"Question {i}?", answer=f"Answer {i}", category="Demo") for i in range(n)]


def test_full_flow_through_widget(widget):
    from gamecenter.games.quiz.logic import Phase

    session = widget._session
    assert session.phase is Phase.JOIN

    widget.handle_buzzer(_event(0))
    widget.handle_buzzer(_event(1))
    assert len(session.players()) == 2

    widget._start_game()
    assert session.phase is Phase.PICK_SET

    # Feed questions directly (skips the threaded fetch) and render QUESTION.
    widget._apply_questions(_questions(2), None)
    assert session.phase is Phase.QUESTION

    # First player buzzes, host reveals early, then judges correct.
    widget.handle_buzzer(_event(0))
    assert session.phase is Phase.ANSWERING
    widget._reveal_now()
    assert session.phase is Phase.REVEAL
    widget._judge(correct=True)
    assert session.phase is Phase.BETWEEN_ROUNDS
    assert session.scores()[1] == 1

    # Second question: nobody knows, skip, then the game is over.
    widget._next_question()
    assert session.phase is Phase.QUESTION
    widget._skip_question()
    assert session.phase is Phase.REVEAL
    widget._judge(correct=False)
    assert session.phase is Phase.GAME_OVER
    assert session.winners()[0].player_id == 1


def test_source_error_returns_to_picker(widget):
    from gamecenter.games.quiz.logic import Phase

    widget.handle_buzzer(_event(0))
    widget._start_game()
    widget._apply_questions([], "boom")
    assert widget._session.phase is Phase.PICK_SET
    assert widget._banner.text == "boom"
