"""Backend selection: turn a config name into a live backend instance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gamecenter.config.models import (
    BACKEND_AUTO,
    BACKEND_EVDEV,
    BACKEND_HIDAPI,
    BACKEND_KEYBOARD,
)
from gamecenter.input.backends.base import BackendUnavailable
from gamecenter.input.backends.evdev_backend import EvdevBackend
from gamecenter.input.backends.hidapi_backend import HidApiBackend
from gamecenter.input.backends.keyboard import KeyboardBackend

if TYPE_CHECKING:
    from gamecenter.config.models import BuzzerConfig
    from gamecenter.input.backends.base import BuzzerBackend, EmitFn

logger = logging.getLogger(__name__)

_BACKENDS = {
    BACKEND_KEYBOARD: KeyboardBackend,
    BACKEND_HIDAPI: HidApiBackend,
    BACKEND_EVDEV: EvdevBackend,
}

# Order tried when the backend is "auto": prefer real hardware, fall back to keyboard.
_AUTO_ORDER = (HidApiBackend, EvdevBackend, KeyboardBackend)


def create_backend(name: str, config: BuzzerConfig, emit: EmitFn) -> BuzzerBackend:
    """Create a backend by name.

    ``"auto"`` picks the first available backend in :data:`_AUTO_ORDER`. An
    explicitly requested backend that is unavailable raises
    :class:`BackendUnavailable`.
    """
    if name == BACKEND_AUTO:
        for backend_cls in _AUTO_ORDER:
            if backend_cls.is_available():
                logger.info("Auto-selected buzzer backend: %s", backend_cls.name)
                return backend_cls(config, emit)
        return KeyboardBackend(config, emit)

    backend_cls = _BACKENDS.get(name)
    if backend_cls is None:
        msg = f"Unknown buzzer backend: {name!r}"
        raise BackendUnavailable(msg)
    if not backend_cls.is_available():
        msg = f"Buzzer backend {name!r} is not available in this environment"
        raise BackendUnavailable(msg)
    return backend_cls(config, emit)
