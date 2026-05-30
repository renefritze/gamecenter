# Usage

## Running the gamecenter

Launch the touchscreen app with the `gamecenter` console command:

```console
$ gamecenter run                  # fullscreen kiosk mode
$ gamecenter run --windowed       # windowed (development)
```

Options:

- `--windowed` — run in a window instead of fullscreen kiosk mode.
- `--backend {auto,keyboard,hidapi,evdev}` — override the buzzer backend.
- `--config PATH` — use an alternate config file.

Without USB buzzers attached, the keyboard fallback maps keys `1`–`4` to
players 1–4, so the launcher and the Reaction Test game are fully usable on a
development machine.

```{toctree}
:maxdepth: 1

examples/basic

```


## Example notebooks statistics

```{nb-exec-table}
```
