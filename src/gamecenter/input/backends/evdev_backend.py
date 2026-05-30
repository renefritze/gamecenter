"""Linux-only buzzer backend built on ``evdev``.

Best for buzzers that enumerate as a keyboard or joystick under
``/dev/input/event*``. The ``evdev`` module is imported lazily and the backend
reports unavailable off-Linux or when the dependency is missing. Which key
codes a given device emits is hardware-specific; the Buzzer Test screen is used
to map physical buzzers to players empirically.
"""

from __future__ import annotations

import importlib.util
import logging
import selectors
import sys
import threading
import time
from typing import TYPE_CHECKING, ClassVar

from gamecenter.core.events import ButtonKind, BuzzerEvent
from gamecenter.input.backends.base import BackendUnavailable, BuzzerBackend, DeviceInfo

if TYPE_CHECKING:
    from gamecenter.config.models import BuzzerConfig
    from gamecenter.input.backends.base import EmitFn

logger = logging.getLogger(__name__)
_KEY_DOWN = 1


class EvdevBackend(BuzzerBackend):
    """Reads input events from ``/dev/input`` devices on a daemon thread."""

    name: ClassVar[str] = "evdev"

    def __init__(self, config: BuzzerConfig, emit: EmitFn) -> None:
        super().__init__(config, emit)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @classmethod
    def is_available(cls) -> bool:
        return sys.platform.startswith("linux") and importlib.util.find_spec("evdev") is not None

    def _devices(self):  # noqa: ANN202 - evdev devices are external untyped handles
        import evdev

        return [evdev.InputDevice(path) for path in evdev.list_devices()]

    def list_devices(self) -> list[DeviceInfo]:
        if not self.is_available():
            return []
        try:
            return [DeviceInfo(device_id=dev.path, name=dev.name, buzzer_count=1) for dev in self._devices()]
        except OSError:
            logger.exception("Failed to enumerate evdev devices")
            return []

    def start(self) -> None:
        if not self.is_available():
            msg = "evdev is unavailable (non-Linux or not installed)"
            raise BackendUnavailable(msg)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="evdev-buzzer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        import evdev

        try:
            devices = self._devices()
        except OSError:
            logger.exception("Failed to open evdev devices")
            return
        if not devices:
            logger.warning("No evdev input devices found")
            return
        selector = selectors.DefaultSelector()
        for index, device in enumerate(devices):
            selector.register(device, selectors.EVENT_READ, (index, device))
        try:
            while not self._stop.is_set():
                for key, _ in selector.select(timeout=0.2):
                    index, device = key.data
                    for raw in device.read():
                        timestamp = time.monotonic()
                        if raw.type == evdev.ecodes.EV_KEY and raw.value == _KEY_DOWN:
                            self._emit(
                                BuzzerEvent(
                                    device_id=device.path,
                                    buzzer_index=index,
                                    button=ButtonKind.BUZZ,
                                    timestamp=timestamp,
                                    raw={"code": raw.code},
                                ),
                            )
        finally:
            for device in devices:
                device.close()
