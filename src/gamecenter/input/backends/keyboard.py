"""Keyboard-emulation backend: the dependency-free, no-hardware fallback.

Events originate on the UI thread (the Kivy ``Window`` feeds key presses into
:meth:`KeyboardBackend.feed_key`), so there is no worker thread and no thread
hop is required. This backend is for development and testing only - real
keyboards buffer/repeat keys and are unsuitable for competitive timing.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar

from gamecenter.core.events import ButtonKind, BuzzerEvent
from gamecenter.input.backends.base import BuzzerBackend, DeviceInfo

if TYPE_CHECKING:
    from gamecenter.config.models import BuzzerConfig
    from gamecenter.input.backends.base import EmitFn


class KeyMap:
    """Pure mapping from key characters to buzzer indices."""

    def __init__(self, mapping: dict[str, int], device_id: str) -> None:
        self._mapping = dict(mapping)
        self._device_id = device_id

    def resolve(self, text: str, *, timestamp: float) -> BuzzerEvent | None:
        """Return a :class:`BuzzerEvent` for ``text``, or ``None`` if unmapped."""
        index = self._mapping.get(text)
        if index is None:
            return None
        return BuzzerEvent(
            device_id=self._device_id,
            buzzer_index=index,
            button=ButtonKind.BUZZ,
            timestamp=timestamp,
        )

    @property
    def device_id(self) -> str:
        """The synthetic device id used for keyboard events."""
        return self._device_id

    @property
    def buzzer_count(self) -> int:
        """Number of distinct buzzers represented in the mapping."""
        return len(set(self._mapping.values()))


class KeyboardBackend(BuzzerBackend):
    """Translates keyboard presses fed by the UI into buzzer events."""

    name: ClassVar[str] = "keyboard"
    accepts_keyboard: ClassVar[bool] = True

    def __init__(self, config: BuzzerConfig, emit: EmitFn) -> None:
        super().__init__(config, emit)
        self._keymap = KeyMap(config.keymap, config.keyboard_device_id)
        self._running = False

    @classmethod
    def is_available(cls) -> bool:
        """The keyboard fallback is always available."""
        return True

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def feed_key(self, text: str) -> bool:
        """Feed a key press from the UI; returns ``True`` if it was a buzzer."""
        if not self._running:
            return False
        event = self._keymap.resolve(text, timestamp=time.monotonic())
        if event is None:
            return False
        self._emit(event)
        return True

    def list_devices(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(
                device_id=self._keymap.device_id,
                name="Keyboard (dev fallback)",
                buzzer_count=self._keymap.buzzer_count,
            ),
        ]
