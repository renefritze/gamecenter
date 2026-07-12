"""Tests for the buzzer manager: fan-out, lifecycle, dispatch hop, hot-swap."""

from __future__ import annotations

import threading

import pytest

from gamecenter.config.models import BACKEND_HIDAPI, BACKEND_KEYBOARD, BuzzerConfig
from gamecenter.core.events import ButtonKind, BuzzerEvent
from gamecenter.input.backends.base import BackendUnavailable
from gamecenter.input.manager import BuzzerManager


def _event() -> BuzzerEvent:
    return BuzzerEvent("kbd", 0, ButtonKind.BUZZ, timestamp=1.0)


def test_subscribe_and_fan_out_via_keyboard_backend():
    manager = BuzzerManager(BuzzerConfig(backend=BACKEND_KEYBOARD))
    seen = []
    manager.subscribe(seen.append)
    manager.start()
    assert manager.feed_key("1") is True
    assert len(seen) == 1
    assert seen[0].buzzer_index == 0


def test_unsubscribe_stops_delivery():
    manager = BuzzerManager(BuzzerConfig(backend=BACKEND_KEYBOARD))
    seen = []
    manager.subscribe(seen.append)
    manager.unsubscribe(seen.append)
    manager.start()
    manager.feed_key("1")
    assert seen == []


def test_dispatch_marshals_to_ui_thread():
    """Events from a worker thread are deferred onto the injected dispatch."""
    pending = []
    manager = BuzzerManager(BuzzerConfig(backend=BACKEND_KEYBOARD), dispatch=pending.append)
    seen = []
    manager.subscribe(seen.append)

    # Simulate a backend emitting from its own thread.
    thread = threading.Thread(target=lambda: manager._on_backend_event(_event()))
    thread.start()
    thread.join()

    # Nothing delivered yet: it is queued on the dispatch (the "UI thread").
    assert seen == []
    assert len(pending) == 1
    # Draining the dispatch delivers the event.
    pending[0]()
    assert len(seen) == 1


def test_subscriber_exception_is_isolated():
    manager = BuzzerManager(BuzzerConfig(backend=BACKEND_KEYBOARD))
    good = []

    def boom(_event):
        raise RuntimeError

    manager.subscribe(boom)
    manager.subscribe(good.append)
    manager.start()
    manager.feed_key("1")
    assert len(good) == 1


def test_set_backend_hot_swaps():
    manager = BuzzerManager(BuzzerConfig(backend=BACKEND_KEYBOARD))
    manager.start()
    manager.set_backend(BACKEND_KEYBOARD)
    assert manager.backend.name == BACKEND_KEYBOARD
    manager.stop()


def test_failed_backend_switch_keeps_current_backend_running(monkeypatch):
    monkeypatch.setattr(
        "gamecenter.input.backends.hidapi_backend.HidApiBackend.is_available", classmethod(lambda _cls: False)
    )
    config = BuzzerConfig(backend=BACKEND_KEYBOARD)
    manager = BuzzerManager(config)
    seen = []
    manager.subscribe(seen.append)
    manager.start()

    with pytest.raises(BackendUnavailable):
        manager.set_backend(BACKEND_HIDAPI)

    assert manager.backend.name == BACKEND_KEYBOARD
    assert config.backend == BACKEND_KEYBOARD
    assert manager.feed_key("1") is True
    assert len(seen) == 1
    manager.stop()
