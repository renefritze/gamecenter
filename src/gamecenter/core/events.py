"""The buzzer event contract shared by every backend and consumer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ButtonKind(str, Enum):
    """Logical button on a buzzer, normalised across device families.

    Game-show buzzers such as the PlayStation "Buzz!" controllers have a big
    BUZZ button plus four coloured answer buttons; generic devices may only
    expose a single button which maps to :attr:`BUZZ`.
    """

    BUZZ = "buzz"
    RED = "red"
    BLUE = "blue"
    ORANGE = "orange"
    GREEN = "green"
    YELLOW = "yellow"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class BuzzerEvent:
    """A single normalised buzzer press.

    ``timestamp`` is captured with :func:`time.monotonic` at the moment the
    backend reads the device, *not* when the event reaches the UI thread, so
    reaction-time measurements reflect true hardware latency.
    """

    device_id: str
    buzzer_index: int
    button: ButtonKind
    timestamp: float
    raw: dict | None = field(default=None, compare=False)

    @property
    def key(self) -> tuple[str, int]:
        """Stable identity of the physical buzzer that produced this event."""
        return (self.device_id, self.buzzer_index)
