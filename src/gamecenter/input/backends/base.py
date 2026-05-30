"""The buzzer backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from gamecenter.config.models import BuzzerConfig
    from gamecenter.core.events import BuzzerEvent

EmitFn = Callable[["BuzzerEvent"], None]


class BackendUnavailable(RuntimeError):
    """Raised when a requested backend cannot run (missing deps or hardware)."""


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Human-facing description of a connected buzzer device."""

    device_id: str
    name: str
    buzzer_count: int


class BuzzerBackend(ABC):
    """Produces :class:`~gamecenter.core.events.BuzzerEvent` objects.

    Backends may read hardware on a worker thread; they deliver events by
    calling the injected ``emit`` callback. ``emit`` is the thread boundary -
    the :class:`~gamecenter.input.manager.BuzzerManager` is responsible for
    hopping events onto the UI thread.
    """

    name: ClassVar[str]

    def __init__(self, config: BuzzerConfig, emit: EmitFn) -> None:
        self._config = config
        self._emit = emit

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Whether this backend can run in the current environment."""

    @abstractmethod
    def start(self) -> None:
        """Begin producing events."""

    @abstractmethod
    def stop(self) -> None:
        """Stop producing events and release the device."""

    @abstractmethod
    def list_devices(self) -> list[DeviceInfo]:
        """Return the currently known devices (may be empty)."""
