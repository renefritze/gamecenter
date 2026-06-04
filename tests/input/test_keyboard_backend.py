"""Tests for the keyboard backend and its pure key map."""

from __future__ import annotations

import pytest

from gamecenter.config.models import BuzzerConfig
from gamecenter.core.events import ButtonKind
from gamecenter.input.backends.keyboard import KeyboardBackend, KeyMap


def test_keymap_resolves_mapped_key():
    keymap = KeyMap({"1": 0, "2": 1}, device_id="kbd")
    event = keymap.resolve("2", timestamp=5.0)
    assert event is not None
    assert event.buzzer_index == 1
    assert event.button is ButtonKind.BUZZ
    assert event.device_id == "kbd"
    assert event.timestamp == pytest.approx(5.0)


def test_keymap_ignores_unmapped_key():
    keymap = KeyMap({"1": 0}, device_id="kbd")
    assert keymap.resolve("x", timestamp=0.0) is None


def test_keyboard_backend_emits_only_when_running():
    emitted = []
    backend = KeyboardBackend(BuzzerConfig(), emitted.append)

    # Not started yet: ignored.
    assert backend.feed_key("1") is False
    assert emitted == []

    backend.start()
    assert backend.feed_key("1") is True
    assert backend.feed_key("9") is False
    assert len(emitted) == 1
    assert emitted[0].buzzer_index == 0


def test_keyboard_backend_always_available():
    assert KeyboardBackend.is_available() is True


def test_keyboard_backend_lists_device():
    backend = KeyboardBackend(BuzzerConfig(), lambda _e: None)
    devices = backend.list_devices()
    assert len(devices) == 1
    assert devices[0].buzzer_count == 4
