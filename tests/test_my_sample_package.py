"""Tests for `my_sample_package` package."""

from click.testing import CliRunner

import my_sample_package
from my_sample_package import cli


def test_version():
    assert my_sample_package.__version__


def test_import():
    pass


def test_command_line_interface():
    """Test the CLI."""
    runner = CliRunner()
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert "my_sample_package.cli.main" in result.output
    help_result = runner.invoke(cli.main, ["--help"])
    assert help_result.exit_code == 0
    assert "--help  Show this message and exit." in help_result.output
