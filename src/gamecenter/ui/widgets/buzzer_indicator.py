"""An indicator that lights up when its buzzer is pressed."""

from __future__ import annotations

from kivy.animation import Animation
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.label import Label

from gamecenter.ui import theme

_IDLE = theme.CARD
_LIT = theme.SUCCESS


class BuzzerIndicator(Label):
    """A coloured panel labelled with a buzzer/player; flashes when pressed."""

    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(text=text, font_size="22sp", color=theme.TEXT, **kwargs)
        with self.canvas.before:
            self._color = Color(*_IDLE)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_args) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size

    def flash(self) -> None:
        """Briefly light the indicator to show its buzzer was pressed."""
        self._color.rgba = _LIT
        Animation(rgba=_IDLE, duration=0.6).start(self._color)
