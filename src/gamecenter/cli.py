"""Console entry point for the gamecenter app.

Kept free of any Kivy import at module load time; the app (and therefore Kivy)
is imported lazily inside the command so the package and tests stay headless.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - typer needs the runtime annotation

import typer

app = typer.Typer(help="Gamecenter: a touchscreen launcher for buzzer party games.")

_BACKENDS = "auto, keyboard, hidapi, evdev"
# Precomputed so the f-string stays out of the function signature default below;
# an f-string default trips sphinx-autoapi's signature parser (JoinedStr).
_BACKEND_HELP = f"Override the buzzer backend ({_BACKENDS})."


@app.callback()
def main() -> None:
    """Gamecenter command-line interface."""
    # A callback keeps ``run`` an explicit subcommand even though it is the only one.


@app.command()
def run(
    windowed: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--windowed",
        help="Run in a window (dev) instead of fullscreen kiosk mode.",
    ),
    backend: str | None = typer.Option(
        None,
        "--backend",
        help=_BACKEND_HELP,
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Use an alternate config file instead of the default location.",
    ),
) -> None:
    """Launch the gamecenter."""
    from gamecenter.ui.app import run_app

    run_app(windowed=windowed, backend_override=backend, config_path=config)


if __name__ == "__main__":  # pragma: no cover
    app()
