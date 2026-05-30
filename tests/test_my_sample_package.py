"""Tests for `my_sample_package` package."""
from click.testing import CliRunner


def test_version():
    import my_sample_package
    assert my_sample_package.__version__


def test_import():
    import my_sample_package


def test_command_line_interface():
    """Test the CLI."""
    from my_sample_package import cli
    runner = CliRunner()
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert 'my_sample_package.cli.main' in result.output
    help_result = runner.invoke(cli.main, ['--help'])
    assert help_result.exit_code == 0
    assert '--help  Show this message and exit.' in help_result.output
