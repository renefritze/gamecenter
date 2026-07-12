"""Tests for the settings service: round-trip, defaults, recovery, observers."""

from __future__ import annotations

import pytest

from gamecenter.config.models import BACKEND_HIDAPI, PlayerSlot
from gamecenter.config.service import SettingsService, config_from_dict


def test_load_missing_file_uses_defaults(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    config = service.load()
    assert config.fullscreen is True
    assert len(config.players) == 4


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "config.json"
    service = SettingsService(path)
    service.load()
    service.config.buzzers.backend = BACKEND_HIDAPI
    service.config.players[0] = PlayerSlot(player_id=0, name="Ann", device_id="kbd", buzzer_index=2)
    service.save()

    reloaded = SettingsService(path)
    config = reloaded.load()
    assert config.buzzers.backend == BACKEND_HIDAPI
    assert config.players[0].name == "Ann"
    assert config.players[0].key == ("kbd", 2)


def test_corrupted_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    service = SettingsService(path)
    config = service.load()
    assert config.fullscreen is True


def test_config_from_dict_tolerates_partial_data():
    config = config_from_dict({"fullscreen": False, "buzzers": {"backend": "evdev"}})
    assert config.fullscreen is False
    assert config.buzzers.backend == "evdev"
    # Missing sections keep their defaults.
    assert config.reaction.min_delay == pytest.approx(2.0)
    # The new game section also defaults when absent.
    assert config.spotify_buzzer.flash_timer_seconds == pytest.approx(10.0)


def test_spotify_buzzer_coercer_falls_back_on_malformed_values():
    config = config_from_dict(
        {
            "spotify_buzzer": {
                "flash_timer_seconds": "not-a-number",
                "target_points": None,
                "points_year_exact": 5,
            }
        }
    )
    # Bad values fall back to defaults; good values are kept.
    assert config.spotify_buzzer.flash_timer_seconds == pytest.approx(10.0)
    assert config.spotify_buzzer.target_points == 15
    assert config.spotify_buzzer.points_year_exact == 5


def test_spotify_buzzer_coercer_keeps_configured_playlist_ids():
    config = config_from_dict(
        {
            "spotify_buzzer": {
                "configured_playlist_ids": ["abc", "", 123, "def"],
            }
        }
    )
    assert config.spotify_buzzer.configured_playlist_ids == ["abc", "def"]


def test_update_notifies_observers(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    service.load()
    seen = []
    service.subscribe(seen.append)
    new = service.config
    new.fullscreen = False
    service.update(new)
    assert len(seen) == 1
    assert seen[0].fullscreen is False


def test_save_is_atomic_no_temp_left_behind(tmp_path):
    path = tmp_path / "config.json"
    service = SettingsService(path)
    service.load()
    service.save()
    leftovers = [p for p in path.parent.iterdir() if p.name.startswith(".config-")]
    assert leftovers == []
