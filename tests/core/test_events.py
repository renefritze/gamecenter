"""Tests for the buzzer event model."""

from __future__ import annotations

from gamecenter.core.events import ButtonKind, BuzzerEvent


def test_event_key_identifies_physical_buzzer():
    event = BuzzerEvent(device_id="hid:1", buzzer_index=2, button=ButtonKind.BUZZ, timestamp=1.0)
    assert event.key == ("hid:1", 2)


def test_raw_is_excluded_from_equality():
    a = BuzzerEvent("d", 0, ButtonKind.RED, 1.0, raw={"x": 1})
    b = BuzzerEvent("d", 0, ButtonKind.RED, 1.0, raw=None)
    assert a == b
