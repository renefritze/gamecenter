"""A small, self-contained visual theme for the Kivy UI.

The app is built from plain Kivy widgets constructed in Python. Rather than
restructure any of that, this module provides drop-in replacements that give
everything a modern, flat look: a coherent dark palette, rounded "flat"
buttons (no Kivy default gradient), and a rounded surface panel/card.

Only colours and a couple of small widget subclasses live here; the screens
keep building their widget trees exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.graphics import Color, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

if TYPE_CHECKING:
    from collections.abc import Sequence

Rgba = tuple[float, float, float, float]

# -- palette ---------------------------------------------------------------
# A modern dark theme. Values are linear Kivy rgba (0..1).
BACKGROUND: Rgba = (0.058, 0.070, 0.121, 1)  # app canvas behind everything
SURFACE: Rgba = (0.105, 0.122, 0.200, 1)  # header/toolbars
CARD: Rgba = (0.137, 0.161, 0.255, 1)  # tiles / raised panels
CARD_DOWN: Rgba = (0.180, 0.208, 0.318, 1)  # card while pressed

PRIMARY: Rgba = (0.357, 0.486, 0.980, 1)  # accent (indigo/blue)
PRIMARY_DOWN: Rgba = (0.290, 0.404, 0.870, 1)
SUCCESS: Rgba = (0.180, 0.760, 0.420, 1)
SUCCESS_DOWN: Rgba = (0.140, 0.640, 0.350, 1)
DANGER: Rgba = (0.890, 0.300, 0.270, 1)
DANGER_DOWN: Rgba = (0.750, 0.220, 0.200, 1)

TEXT: Rgba = (0.960, 0.970, 1.000, 1)
TEXT_MUTED: Rgba = (0.600, 0.640, 0.780, 1)
ON_PRIMARY: Rgba = (1, 1, 1, 1)

# Named button variants: (idle fill, pressed fill, text colour).
_VARIANTS: dict[str, tuple[Rgba, Rgba, Rgba]] = {
    "primary": (PRIMARY, PRIMARY_DOWN, ON_PRIMARY),
    "secondary": (CARD, CARD_DOWN, TEXT),
    "success": (SUCCESS, SUCCESS_DOWN, ON_PRIMARY),
    "danger": (DANGER, DANGER_DOWN, ON_PRIMARY),
}


def _follow(widget, rect: RoundedRectangle) -> None:
    """Keep ``rect`` aligned with ``widget`` as it moves/resizes."""

    def _sync(instance, _value) -> None:
        rect.pos = instance.pos
        rect.size = instance.size

    widget.bind(pos=_sync, size=_sync)
    _sync(widget, None)


class StyledButton(Button):
    """A flat, rounded button that replaces Kivy's gradient default.

    Same construction/usage as :class:`kivy.uix.button.Button`; just pass an
    optional ``variant`` (``primary``/``secondary``/``success``/``danger``).
    """

    def __init__(self, *, variant: str = "primary", radius: int = 12, **kwargs) -> None:
        kwargs.setdefault("font_size", "20sp")
        super().__init__(**kwargs)
        self._radius = radius
        # Hide Kivy's built-in textured background so only our rounded fill shows.
        self.background_color = (0, 0, 0, 0)
        with self.canvas.before:
            self._fill = Color(*PRIMARY)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        _follow(self, self._rect)
        self.bind(state=lambda *_: self._paint())
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        """Switch the colour scheme (used e.g. for selected/toggle states)."""
        self._variant = variant if variant in _VARIANTS else "primary"
        self.color = _VARIANTS[self._variant][2]
        self._paint()

    def _paint(self) -> None:
        idle, down, _text = _VARIANTS[self._variant]
        self._fill.rgba = down if self.state == "down" else idle


class Panel(BoxLayout):
    """A :class:`BoxLayout` with a solid (optionally rounded) background.

    Used for header bars and raised surfaces so screens read as panels on the
    dark canvas instead of floating, borderless widgets.
    """

    def __init__(self, *, bg: Rgba = SURFACE, radius: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        with self.canvas.before:
            self._bg = Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        _follow(self, self._rect)


def attach_rounded_bg(
    widget,
    *,
    idle: Rgba,
    down: Sequence[float] | None = None,
    radius: int = 16,
) -> Color:
    """Give an existing widget a rounded background that follows its geometry.

    Returns the :class:`Color` instruction so callers can animate it. If
    ``down`` is given and the widget exposes a ``state``, the fill swaps to it
    while pressed.
    """
    with widget.canvas.before:
        color = Color(*idle)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    _follow(widget, rect)
    if down is not None and hasattr(widget, "state"):

        def _on_state(_w, state) -> None:
            color.rgba = tuple(down) if state == "down" else idle

        widget.bind(state=_on_state)
    return color
