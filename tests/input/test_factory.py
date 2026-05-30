"""Tests for buzzer backend selection."""

from __future__ import annotations

import pytest

from gamecenter.config.models import (
    BACKEND_AUTO,
    BACKEND_EVDEV,
    BACKEND_HIDAPI,
    BACKEND_KEYBOARD,
    BuzzerConfig,
)
from gamecenter.input.backends import factory
from gamecenter.input.backends.base import BackendUnavailable
from gamecenter.input.backends.keyboard import KeyboardBackend


def _noop(_event):
    pass


def test_auto_falls_back_to_keyboard_when_hardware_unavailable(monkeypatch):
    monkeypatch.setattr(
        "gamecenter.input.backends.hidapi_backend.HidApiBackend.is_available", classmethod(lambda _cls: False)
    )
    monkeypatch.setattr(
        "gamecenter.input.backends.evdev_backend.EvdevBackend.is_available", classmethod(lambda _cls: False)
    )
    backend = factory.create_backend(BACKEND_AUTO, BuzzerConfig(), _noop)
    assert isinstance(backend, KeyboardBackend)


def test_auto_prefers_hidapi_when_available(monkeypatch):
    monkeypatch.setattr(
        "gamecenter.input.backends.hidapi_backend.HidApiBackend.is_available", classmethod(lambda _cls: True)
    )
    backend = factory.create_backend(BACKEND_AUTO, BuzzerConfig(), _noop)
    assert backend.name == BACKEND_HIDAPI


def test_explicit_unavailable_backend_raises(monkeypatch):
    monkeypatch.setattr(
        "gamecenter.input.backends.evdev_backend.EvdevBackend.is_available", classmethod(lambda _cls: False)
    )
    with pytest.raises(BackendUnavailable):
        factory.create_backend(BACKEND_EVDEV, BuzzerConfig(), _noop)


def test_keyboard_always_creatable():
    backend = factory.create_backend(BACKEND_KEYBOARD, BuzzerConfig(), _noop)
    assert isinstance(backend, KeyboardBackend)


def test_unknown_backend_raises():
    with pytest.raises(BackendUnavailable):
        factory.create_backend("bogus", BuzzerConfig(), _noop)
