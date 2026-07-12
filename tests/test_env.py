"""Tests for local dotenv loading."""

from __future__ import annotations

import os

import pytest

from gamecenter.env import env_flag, load_dotenv


def test_load_dotenv_sets_missing_values(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        """# ignored
SPOTIFY_CLIENT_ID=abc123
export SPOTIFY_REDIRECT_URI='http://127.0.0.1:8888/callback'
QUOTED="hello\\nworld"
INLINE=value # comment
""",
        encoding="utf-8",
    )

    loaded = load_dotenv(dotenv)

    assert loaded == 4
    assert os.environ["SPOTIFY_CLIENT_ID"] == "abc123"
    assert os.environ["SPOTIFY_REDIRECT_URI"] == "http://127.0.0.1:8888/callback"
    assert os.environ["QUOTED"] == "hello\nworld"
    assert os.environ["INLINE"] == "value"


def test_load_dotenv_does_not_override_existing_values(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SPOTIFY_CLIENT_ID=from-file\n", encoding="utf-8")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "from-env")

    assert load_dotenv(dotenv) == 0
    assert os.environ["SPOTIFY_CLIENT_ID"] == "from-env"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
def test_env_flag_enabled_values(value, monkeypatch):
    monkeypatch.setenv("FLAG", value)

    assert env_flag("FLAG") is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "anything"])
def test_env_flag_disabled_values(value, monkeypatch):
    monkeypatch.setenv("FLAG", value)

    assert env_flag("FLAG") is False


def test_env_flag_unset_is_disabled(monkeypatch):
    monkeypatch.delenv("FLAG", raising=False)

    assert env_flag("FLAG") is False
