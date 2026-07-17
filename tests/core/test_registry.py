"""Tests for the game and service registries."""

from __future__ import annotations

import pytest

from gamecenter.core.game_api import Game, GameMeta
from gamecenter.core.registry import GameRegistry, ServiceRegistry
from gamecenter.core.service_api import Service


class _FakeGame(Game):
    meta = GameMeta(id="fake", title="Zed Game", description="d", needs_buzzers=False)

    def build_widget(self, context):
        return None

    def start(self, context):
        # No-op: registry tests don't run the game lifecycle.
        pass

    def stop(self):
        # No-op: registry tests don't run the game lifecycle.
        pass


def test_register_and_create():
    registry = GameRegistry()
    registry.register(_FakeGame)
    assert registry.create("fake").meta.id == "fake"


def test_load_builtin_includes_reaction():
    registry = GameRegistry()
    registry.load_builtin()
    ids = {meta.id for meta in registry.all()}
    assert "reaction" in ids
    assert "quiz" in ids


def test_all_is_sorted_by_title():
    registry = GameRegistry()
    registry.register(_FakeGame)
    registry.load_builtin()
    titles = [meta.title for meta in registry.all()]
    assert titles == sorted(titles)


class _FakeService(Service):
    id = "svc"

    def __init__(self):
        self.started = False

    @classmethod
    def is_available(cls):
        return True

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


def test_service_registry_start_stop():
    registry = ServiceRegistry()
    service = _FakeService()
    registry.register(service)
    assert registry.get("svc") is service
    registry.start_all()
    assert service.started is True
    registry.stop_all()
    assert service.started is False


def test_create_unknown_game_raises():
    with pytest.raises(KeyError):
        GameRegistry().create("nope")
