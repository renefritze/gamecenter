"""Kivy view for the Trivia Quiz game.

A thin layer over :class:`gamecenter.games.quiz.logic.QuizSession`: it owns the
Kivy ``Clock`` (the flashing answer countdown and the threaded question fetch),
renders one panel per phase, and translates touches and buzzer events into pure
logic calls. Question sets are loaded via :mod:`gamecenter.games.quiz.sources`
on a background thread so a slow network never blocks the UI.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from gamecenter.games.quiz import sources
from gamecenter.games.quiz.logic import Phase, QuizSession
from gamecenter.games.quiz.sources import QuizSourceError
from gamecenter.ui import theme
from gamecenter.ui.theme import Panel, StyledButton

if TYPE_CHECKING:
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.core.game_api import GameContext
    from gamecenter.games.quiz.sources import QuestionSetInfo, QuizQuestion

logger = logging.getLogger(__name__)

# Full-screen background tints per phase.
_BG_NEUTRAL = theme.BACKGROUND
_BG_QUESTION = (0.105, 0.122, 0.200, 1)
_BG_FLASH_A = (0.690, 0.180, 0.180, 1)
_BG_FLASH_B = (0.180, 0.208, 0.318, 1)
_BG_DONE = (0.137, 0.161, 0.255, 1)


class QuizWidget(BoxLayout):
    """Renders the Trivia Quiz session, one panel per phase."""

    def __init__(self, context: GameContext, **kwargs) -> None:
        super().__init__(orientation="vertical", padding=16, spacing=12, **kwargs)
        self._context = context
        self._session: QuizSession | None = None
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

    # -- lifecycle ----------------------------------------------------------
    def begin(self) -> None:
        config = self._context.settings.config.quiz
        self._session = QuizSession(config, known_players=self._context.players)
        self._render()

    def shutdown(self) -> None:
        self._cancel_countdown()
        # Drop the session so any late background-load callback returns early.
        self._session = None

    # -- buzzer input -------------------------------------------------------
    def handle_buzzer(self, event: BuzzerEvent) -> None:
        session = self._session
        if session is None:
            return
        if session.phase is Phase.JOIN:
            if session.join_buzz(event.device_id, event.buzzer_index) is not None:
                self._render_join()
        elif session.phase is Phase.QUESTION:
            player = session.player_for(event.device_id, event.buzzer_index)
            if player is not None and session.buzz(player.player_id):
                self._enter_answering()

    # -- rendering dispatch -------------------------------------------------
    def _render(self) -> None:
        self._cancel_countdown()
        phase = self._session.phase if self._session else None
        if phase is Phase.JOIN:
            self._render_join()
        elif phase is Phase.PICK_SET:
            self._render_pick_set()
        elif phase is Phase.QUESTION:
            self._render_question()
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

    @staticmethod
    def _wrapped_label(text: str, *, font_size: str = "28sp", color=theme.TEXT, bold: bool = False) -> Label:
        """Build a centred label that wraps its text to the available width."""
        label = Label(text=text, font_size=font_size, color=color, bold=bold, halign="center", valign="middle")
        label.bind(size=lambda widget, size: setattr(widget, "text_size", (size[0], None)))
        return label

    # -- phases -------------------------------------------------------------
    def _render_join(self) -> None:
        session = self._session
        body = self._fresh_content("Press your buzzer to join", _BG_NEUTRAL)
        players = session.players() if session else []
        roster = "\n".join(p.display_name for p in players) or "No players yet..."
        body.add_widget(Label(text=roster, font_size="24sp", color=theme.TEXT))
        start = StyledButton(text="Start game", variant="success", size_hint_y=None, height=72)
        start.disabled = not players
        start.bind(on_release=lambda *_: self._start_game())
        body.add_widget(start)

    def _start_game(self) -> None:
        if self._session and self._session.finish_join():
            self._render()

    def _render_pick_set(self) -> None:
        body = self._fresh_content("Pick a question set", _BG_NEUTRAL)
        config = self._context.settings.config.quiz
        for info in sources.available_sets(config):
            button = StyledButton(text=info.name, variant="secondary", size_hint_y=None, height=64)
            button.bind(on_release=lambda _b, chosen=info: self._choose_set(chosen))
            body.add_widget(button)
        body.add_widget(BoxLayout())  # spacer

    def _choose_set(self, info: QuestionSetInfo) -> None:
        self._fresh_content("Loading questions...", _BG_NEUTRAL)
        config = self._context.settings.config.quiz

        def worker() -> None:
            try:
                result, error = sources.load_questions(info, config), None
            except QuizSourceError as exc:
                result, error = [], str(exc)
            except Exception:
                logger.exception("Unexpected error loading quiz questions")
                result, error = [], "Could not load questions; try another set."
            Clock.schedule_once(lambda _dt: self._apply_questions(result, error), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_questions(self, questions: list[QuizQuestion], error: str | None) -> None:
        if self._session is None or self._session.phase is not Phase.PICK_SET:
            return
        if error or not questions:
            self._show_error(error or "That set has no questions. Pick another.")
            self._render_pick_set()
            return
        if self._session.set_questions(questions):
            self._clear_error()
            self._render()

    def _render_question(self) -> None:
        session = self._session
        question = session.current_question if session else None
        if session is None or question is None:
            return
        body = self._fresh_content(f"Question {session.question_number} / {session.total_questions}", _BG_QUESTION)
        if question.category:
            body.add_widget(
                Label(text=question.category, font_size="20sp", color=theme.TEXT_MUTED, size_hint_y=None, height=32)
            )
        body.add_widget(self._wrapped_label(question.text, font_size="32sp", bold=True))
        body.add_widget(self._scoreboard())
        skip = StyledButton(text="Nobody knows - show answer", variant="secondary", size_hint_y=None, height=64)
        skip.bind(on_release=lambda *_: self._skip_question())
        body.add_widget(skip)

    def _skip_question(self) -> None:
        if self._session and self._session.skip_question():
            self._render()

    def _enter_answering(self) -> None:
        config = self._context.settings.config.quiz
        self._answer_deadline = time.monotonic() + config.answer_timeout_seconds
        self._render_answering()
        self._countdown_event = Clock.schedule_interval(self._tick_answer, 0.05)

    def _render_answering(self) -> None:
        session = self._session
        answerer = session.answering_player if session else None
        name = answerer.display_name if answerer else "Player"
        body = self._fresh_content(f"{name}, your answer!", _BG_FLASH_A)
        question = session.current_question if session else None
        if question is not None:
            body.add_widget(self._wrapped_label(question.text, font_size="26sp"))
        self._countdown_label = Label(text="", font_size="72sp", bold=True, color=theme.TEXT)
        body.add_widget(self._countdown_label)
        reveal = StyledButton(text="Show answer now", variant="primary", size_hint_y=None, height=72)
        reveal.bind(on_release=lambda *_: self._reveal_now())
        body.add_widget(reveal)

    def _tick_answer(self, _dt: float) -> None:
        if self._answer_deadline is None or self._session is None:
            return
        remaining = self._answer_deadline - time.monotonic()
        if remaining <= 0:
            self._cancel_countdown()
            if self._session.timeout_expired():
                self._render()
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
        question = session.current_question if session else None
        if session is None or question is None:
            return
        body = self._fresh_content("Answer", _BG_DONE)
        body.add_widget(self._wrapped_label(question.text, font_size="24sp", color=theme.TEXT_MUTED))
        body.add_widget(self._wrapped_label(question.answer, font_size="36sp", bold=True))
        answerer = session.answering_player
        if answerer is not None:
            body.add_widget(
                Label(
                    text=f"Was {answerer.display_name} correct?",
                    font_size="24sp",
                    color=theme.TEXT,
                    size_hint_y=None,
                    height=40,
                )
            )
            row = BoxLayout(size_hint_y=None, height=72, spacing=12)
            yes = StyledButton(text="Correct", variant="success")
            yes.bind(on_release=lambda *_: self._judge(correct=True))
            no = StyledButton(text="Wrong", variant="danger")
            no.bind(on_release=lambda *_: self._judge(correct=False))
            row.add_widget(yes)
            row.add_widget(no)
            body.add_widget(row)
        else:
            cont = StyledButton(text="Continue", variant="primary", size_hint_y=None, height=72)
            cont.bind(on_release=lambda *_: self._judge(correct=False))
            body.add_widget(cont)

    def _judge(self, *, correct: bool) -> None:
        if self._session is None:
            return
        if self._session.judge(correct=correct) is not None:
            self._render()

    def _render_between_rounds(self) -> None:
        body = self._fresh_content("Scores", _BG_DONE)
        body.add_widget(self._scoreboard())
        nxt = StyledButton(text="Next question", variant="primary", size_hint_y=None, height=72)
        nxt.bind(on_release=lambda *_: self._next_question())
        body.add_widget(nxt)

    def _next_question(self) -> None:
        if self._session and self._session.next_question():
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

    def _show_error(self, message: str) -> None:
        self._banner.text = message
        self._banner.height = 32

    def _clear_error(self) -> None:
        self._banner.text = ""
        self._banner.height = 0
