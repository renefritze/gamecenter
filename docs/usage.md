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

:::{warning}
The `evdev` backend currently listens to every `/dev/input/event*` device,
including mice and touchpads. On the Buzzer Test screen, clicking a player can
assign the mouse to that player; later mouse or touch activity may then be
reported as a buzz. Use `hidapi` for PlayStation Buzz! controllers, or
`keyboard` with keys `1`–`4` for development testing.
:::

## PlayStation Buzz! receivers on Linux

The `hidapi` backend supports Sony PlayStation Buzz! receivers such as
`054c:1000`. If `lsusb` shows the receiver but the app logs that it cannot open
the HID device, install a udev rule and reinsert the receiver:

```console
$ sudo tee /etc/udev/rules.d/60-gamecenter-buzz.rules >/dev/null <<'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="1000", MODE="0660", GROUP="input", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0002", MODE="0660", GROUP="input", TAG+="uaccess"
EOF
$ sudo udevadm control --reload-rules
$ sudo udevadm trigger
```

```{toctree}
:maxdepth: 1

examples/basic

```


## Example notebooks statistics

```{nb-exec-table}
```
