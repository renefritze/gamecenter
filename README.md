gamecenter
==========


[![image](https://github.com/renefritze/gamecenter/workflows/pytest/badge.svg)](https://github.com/renefritze/gamecenter/actions)


A full-screen, touchscreen launcher for buzzer party games — built for a
Raspberry Pi with a touchscreen, but also runnable in a window on a Linux
desktop for development.


Features
--------

- **Touch launcher** with a grid of bundled games and a settings subscreen.
- **USB game-show buzzer support** via a pluggable backend layer
  (`hidapi`, `evdev`, and a dependency-free keyboard fallback so the whole app
  is usable with no hardware attached).
- **Buzzer Test screen** to identify and map each physical buzzer to a player.
- **Reaction Test** game as the initial demo: wait for green, then race to buzz.
- Clean extension seams (a game registry + a service registry) for future
  features such as USB webcam and Spotify integration.


Quick start
-----------

```console
$ pip install -e '.[dev]'         # add ',hardware' for real USB buzzers
$ gamecenter run --windowed       # dev: windowed, keyboard buzzers (keys 1-4)
$ gamecenter run                  # kiosk: fullscreen
```

CLI options: `--windowed`, `--backend {auto,keyboard,hidapi,evdev}`,
`--config PATH`.

`gamecenter demo` runs a scripted UI tour (launcher → settings → buzzer test →
Reaction game) that drives the app and exits on its own. It is meant to be
screen-recorded: the manually-dispatched **UI video** GitHub Actions workflow
(`.github/workflows/ui-video.yml`) runs it under Xvfb, captures the screen with
ffmpeg and uploads the resulting MP4 as a build artifact.

On a Raspberry Pi you also need the SDL2 system libraries that Kivy depends on
(`libsdl2`, `libsdl2-image`, `libsdl2-mixer`, `libsdl2-ttf`); see the Kivy
installation docs for your OS image.


Architecture
------------

- `gamecenter.core` / `config` / `input` — pure, Kivy-free logic (the
  headless-testable core: buzzer events, the buzzer manager, config, scoring).
- `gamecenter.ui` — the Kivy app shell, screens and widgets.
- `gamecenter.games` — bundled games; each implements a common `Game` interface
  and is discovered by the launcher's registry.

Kivy is never imported at package import time, so the test suite runs headless.
Run `pytest` for the core suite; run the display-backed smoke tests with
`xvfb-run -a pytest -m gui`.


Credits
-------

This package was created with
[Cookiecutter](https://github.com/audreyr/cookiecutter) and the
[renefritze/python_cookiecutter](https://github.com/renefritze/python_cookiecutter)
project template.
