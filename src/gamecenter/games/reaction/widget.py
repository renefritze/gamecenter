"""Kivy view for the Reaction Test game.

Thin layer over :class:`gamecenter.games.reaction.logic.ReactionRound`: it owns
the Kivy ``Clock`` timers and colours, but every timing/scoring decision lives
in the pure logic. Buzzer timestamps (monotonic, captured at the backend) flow
straight into the round, so reaction times reflect real hardware latency.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from gamecenter.games.reaction.logic import Phase, ReactionRound, resolve_player_id

if TYPE_CHECKING:
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.core.game_api import GameContext

# Semantic full-screen states, tuned to sit alongside the app palette.
_WAIT_COLOR = (0.690, 0.180, 0.180, 1)
_GO_COLOR = (0.180, 0.760, 0.420, 1)
_DONE_COLOR = (0.137, 0.161, 0.255, 1)


class ReactionWidget(BoxLayout):
    """Displays the reaction round and renders results."""

    def __init__(self, context: GameContext, **kwargs) -> None:
        super().__init__(orientation="vertical", **kwargs)
        self._context = context
        self._round: ReactionRound | None = None
        self._go_event = None
        self._timeout_event = None

        with self.canvas.before:
            self._color = Color(*_WAIT_COLOR)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

        self._headline = Label(text="Get ready...", font_size="64sp", bold=True)
        self._detail = Label(text="", font_size="28sp")
        self.add_widget(self._headline)
        self.add_widget(self._detail)

    def _sync(self, *_args) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size

    def begin(self) -> None:
        """Arm a fresh round and schedule the GO signal."""
        config = self._context.settings.config.reaction
        player_ids = [slot.player_id for slot in self._context.players]
        self._round = ReactionRound(player_ids, config)
        self._set_color(_WAIT_COLOR)
        self._headline.text = "Wait for green..."
        self._detail.text = ""
        delay = self._round.arm(time.monotonic()) - time.monotonic()
        self._go_event = Clock.schedule_once(self._fire_go, max(0.0, delay))

    def _fire_go(self, _dt: float) -> None:
        if self._round is None:
            return
        self._round.on_go(time.monotonic())
        self._set_color(_GO_COLOR)
        self._headline.text = "GO!"
        timeout = self._context.settings.config.reaction.round_timeout
        self._timeout_event = Clock.schedule_once(lambda _dt: self._finish(), timeout)

    def handle_buzzer(self, event: BuzzerEvent) -> None:
        """Feed a buzzer press into the round and update the display."""
        if self._round is None or self._round.phase is Phase.FINISHED:
            return
        player_id = resolve_player_id(self._context.players, event.device_id, event.buzzer_index)
        if player_id is None:
            return
        was_waiting = self._round.phase is Phase.WAIT
        self._round.on_buzz(player_id, event.timestamp)
        if was_waiting:
            self._detail.text = f"Player {player_id} jumped the gun!"
        elif self._round.all_in:
            self._finish()

    def _finish(self) -> None:
        if self._round is None:
            return
        results = self._round.finish()
        self._set_color(_DONE_COLOR)
        self._headline.text = "Results"
        lines = []
        for result in results:
            if result.has_time:
                lines.append(f"{result.rank}. Player {result.player_id}: {result.reaction_ms:.0f} ms")
            elif result.false_start:
                lines.append(f"-  Player {result.player_id}: false start")
            else:
                lines.append(f"-  Player {result.player_id}: no buzz")
        self._detail.text = "\n".join(lines)

    def shutdown(self) -> None:
        """Cancel pending timers (called when the game stops)."""
        for event in (self._go_event, self._timeout_event):
            if event is not None:
                event.cancel()
        self._go_event = None
        self._timeout_event = None

    def _set_color(self, rgba: tuple[float, float, float, float]) -> None:
        self._color.rgba = rgba
