"""Cross-platform USB HID buzzer backend built on ``hidapi``.

The ``hid`` module is imported lazily so the package installs and tests without
it. Report decoding is necessarily hardware-specific: the included decoder
targets PlayStation "Buzz!"-style controllers (one dongle, four buzzers, a big
BUZZ button plus four coloured buttons). Other devices will need their report
layout added here - the Buzzer Test screen is the tool for discovering it.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
import time
from typing import TYPE_CHECKING, ClassVar

from gamecenter.core.events import ButtonKind, BuzzerEvent
from gamecenter.input.backends.base import BackendUnavailable, BuzzerBackend, DeviceInfo

if TYPE_CHECKING:
    from gamecenter.config.models import BuzzerConfig
    from gamecenter.input.backends.base import EmitFn

logger = logging.getLogger(__name__)

# Sony Buzz! controllers; the second product id is the wireless dongle.
_BUZZ_VENDOR_ID = 0x054C
_BUZZ_PRODUCT_IDS = (0x0002, 0x1000)

# Per-buzzer coloured-button order matching ButtonKind for Buzz! controllers.
_BUZZ_BUTTON_ORDER = (
    ButtonKind.BUZZ,
    ButtonKind.YELLOW,
    ButtonKind.GREEN,
    ButtonKind.ORANGE,
    ButtonKind.BLUE,
)
_BUTTONS_PER_BUZZER = len(_BUZZ_BUTTON_ORDER)
_READ_TIMEOUT_MS = 200
# Button states live in the last three bytes of the report (bytes 2..4).
_MIN_REPORT_LEN = 5
_LINUX_UDEV_HINT = (
    'add a udev rule such as SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", '
    'ATTRS{idProduct}=="1000", MODE="0660", GROUP="input", TAG+="uaccess"'
)


class HidApiBackend(BuzzerBackend):
    """Reads HID buzzer reports on a daemon thread."""

    name: ClassVar[str] = "hidapi"

    def __init__(self, config: BuzzerConfig, emit: EmitFn) -> None:
        super().__init__(config, emit)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._device_id = "hid"
        self._prev_state: tuple[bool, ...] = ()

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("hid") is not None

    def list_devices(self) -> list[DeviceInfo]:
        if not self.is_available():
            return []

        return [
            DeviceInfo(
                device_id=_decode_hid_path(info.get("path", b"")),
                name=info.get("product_string") or "Buzz! controller",
                buzzer_count=4,
            )
            for info in _buzz_devices()
        ]

    def start(self) -> None:
        if not self.is_available():
            msg = "hidapi is not installed"
            raise BackendUnavailable(msg)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hidapi-buzzer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None

    # Returns an external, untyped hid.device handle (or None).
    def _open(self):  # noqa: ANN202
        import hid

        devices = _buzz_devices()
        for info in devices:
            device = hid.device()
            try:
                device.open_path(info["path"])
            except OSError as exc:
                logger.warning("Found HID buzzer %s but could not open it: %s", _device_label(info), exc)
                device.close()
                continue
            product_id = int(info.get("product_id", 0))
            self._device_id = f"hid:{_BUZZ_VENDOR_ID:04x}:{product_id:04x}"
            device.set_nonblocking(False)
            return device
        if devices:
            logger.warning("HID buzzer receiver is visible but not readable; on Linux, %s", _LINUX_UDEV_HINT)
        return None

    def _run(self) -> None:
        try:
            device = self._open()
        except OSError:
            logger.exception("Failed to open HID buzzer device")
            return
        if device is None:
            logger.warning("No HID buzzer device found")
            return
        try:
            while not self._stop.is_set():
                report = device.read(64, _READ_TIMEOUT_MS)
                timestamp = time.monotonic()
                if report:
                    self._dispatch_report(bytes(report), timestamp)
        finally:
            device.close()

    def _dispatch_report(self, report: bytes, timestamp: float) -> None:
        state = decode_buzz_report(report)
        for index, pressed in enumerate(state):
            was_pressed = index < len(self._prev_state) and self._prev_state[index]
            if pressed and not was_pressed:
                buzzer_index, button = divmod(index, _BUTTONS_PER_BUZZER)
                self._emit(
                    BuzzerEvent(
                        device_id=self._device_id,
                        buzzer_index=buzzer_index,
                        button=_BUZZ_BUTTON_ORDER[button],
                        timestamp=timestamp,
                        raw={"report": report.hex()},
                    ),
                )
        self._prev_state = state


def decode_buzz_report(report: bytes) -> tuple[bool, ...]:
    """Decode a Buzz! controller report into per-button pressed flags.

    Buzz! controllers pack the 20 button states (4 buzzers x 5 buttons) into
    the last three bytes of the report. Returns a flat tuple indexed as
    ``buzzer * 5 + button``. Pure function so it is unit-testable without
    hardware.
    """
    if len(report) < _MIN_REPORT_LEN:
        return ()
    bits = report[2] | (report[3] << 8) | (report[4] << 16)
    return tuple(bool(bits & (1 << i)) for i in range(_BUTTONS_PER_BUZZER * 4))


def _buzz_devices() -> list[dict]:
    import hid

    return [
        info
        for info in hid.enumerate()
        if info.get("vendor_id") == _BUZZ_VENDOR_ID and info.get("product_id") in _BUZZ_PRODUCT_IDS
    ]


def _decode_hid_path(path: object) -> str:
    if isinstance(path, bytes):
        return path.decode("utf-8", "replace")
    return str(path)


def _device_label(info: dict) -> str:
    product_id = int(info.get("product_id", 0))
    path = _decode_hid_path(info.get("path", b""))
    return f"054c:{product_id:04x} at {path}"
