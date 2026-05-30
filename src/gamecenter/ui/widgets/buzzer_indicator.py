"""An indicator that lights up when its buzzer is pressed."""

from __future__ import annotations

from kivy.animation import Animation
from kivy.graphics import Color, Rectangle
from kivy.uix.label import Label

_IDLE = (0.2, 0.2, 0.2, 1)
_LIT = (0.1, 0.8, 0.2, 1)


class BuzzerIndicator(Label):
    """A coloured panel labelled with a buzzer/player; flashes when pressed."""

    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(text=text, font_size="22sp", **kwargs)
        with self.canvas.before:
            self._color = Color(*_IDLE)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_args) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size

    def flash(self) -> None:
        """Briefly light the indicator to show its buzzer was pressed."""
        self._color.rgba = _LIT
        Animation(rgba=_IDLE, duration=0.6).start(self._color)
