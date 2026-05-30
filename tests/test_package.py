"""Top-level package and CLI tests."""

from __future__ import annotations

import sys

from typer.testing import CliRunner

import gamecenter
from gamecenter import cli


def test_version():
    assert gamecenter.__version__


def test_cli_help():
    result = CliRunner().invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "gamecenter" in result.output.lower()


def test_importing_core_does_not_pull_in_kivy():
    """Importing the package and its core must stay display-free."""
    # Importing these modules must not drag Kivy into the process.
    import gamecenter.config.service
    import gamecenter.core.registry
    import gamecenter.games.reaction.logic
    import gamecenter.input.manager  # noqa: F401

    assert "kivy" not in sys.modules
