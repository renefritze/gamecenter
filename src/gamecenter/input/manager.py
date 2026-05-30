"""The buzzer manager: backend lifecycle, the thread hop, and fan-out.

Kivy-free. Backends may emit events from worker threads; the manager marshals
them onto a single dispatch callable (the Kivy app injects one backed by
``Clock.schedule_once``; tests inject a synchronous one) before fanning out to
subscribers, so subscribers always run on the UI thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from gamecenter.input.backends.factory import create_backend

if TYPE_CHECKING:
    from gamecenter.config.models import BuzzerConfig
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.input.backends.base import BuzzerBackend, DeviceInfo

logger = logging.getLogger(__name__)

Subscriber = Callable[["BuzzerEvent"], None]
# A dispatch hops a zero-arg callable onto the UI thread.
Dispatch = Callable[[Callable[[], None]], None]


def _synchronous_dispatch(fn: Callable[[], None]) -> None:
    fn()


class BuzzerManager:
    """Owns the active backend and fans buzzer events out to subscribers."""

    def __init__(self, config: BuzzerConfig, dispatch: Dispatch | None = None) -> None:
        """Create a manager and its backend; ``dispatch`` hops events to the UI thread."""
        self._config = config
        self._dispatch = dispatch or _synchronous_dispatch
        self._subscribers: list[Subscriber] = []
        self._backend: BuzzerBackend = create_backend(config.backend, config, self._on_backend_event)
        self._running = False

    @property
    def backend(self) -> BuzzerBackend:
        """The currently active backend."""
        return self._backend

    def subscribe(self, callback: Subscriber) -> None:
        """Register a callback for buzzer events (invoked on the UI thread)."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        """Remove a previously registered subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def start(self) -> None:
        """Start the active backend."""
        if self._running:
            return
        self._backend.start()
        self._running = True

    def stop(self) -> None:
        """Stop the active backend."""
        if not self._running:
            return
        self._backend.stop()
        self._running = False

    def set_backend(self, name: str) -> None:
        """Hot-swap to a different backend, restarting if currently running."""
        was_running = self._running
        self.stop()
        self._config.backend = name
        self._backend = create_backend(name, self._config, self._on_backend_event)
        if was_running:
            self.start()

    def list_devices(self) -> list[DeviceInfo]:
        """Devices known to the active backend."""
        return self._backend.list_devices()

    def feed_key(self, text: str) -> bool:
        """Feed a keyboard key to the backend if it accepts keyboard input."""
        feed = getattr(self._backend, "feed_key", None)
        if callable(feed):
            return bool(feed(text))
        return False

    def _on_backend_event(self, event: BuzzerEvent) -> None:
        # Called from the backend's thread; hop to the UI thread before fan-out.
        self._dispatch(lambda: self._fan_out(event))

    def _fan_out(self, event: BuzzerEvent) -> None:
        for subscriber in list(self._subscribers):
            self._notify_one(subscriber, event)

    @staticmethod
    def _notify_one(subscriber: Subscriber, event: BuzzerEvent) -> None:
        try:
            subscriber(event)
        except Exception:
            logger.exception("Buzzer subscriber raised")
