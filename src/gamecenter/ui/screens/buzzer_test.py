"""The buzzer test/identify screen.

Subscribes to buzzer events while visible; flashes the indicator for the player
the pressed buzzer resolves to, shows the raw device/index/button, and lets the
operator assign the last-pressed physical buzzer to a player slot.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from gamecenter.games.reaction.logic import resolve_player_id
from gamecenter.ui import ScreenName
from gamecenter.ui.widgets.buzzer_indicator import BuzzerIndicator

if TYPE_CHECKING:
    from gamecenter.core.events import BuzzerEvent
    from gamecenter.ui.app import GameCenterApp


class BuzzerTestScreen(Screen):
    """Identify and map physical buzzers to players."""

    def __init__(self, app: GameCenterApp, **kwargs) -> None:
        super().__init__(**kwargs)
        self._app = app
        self._last_event: BuzzerEvent | None = None
        self._indicators: dict[int, BuzzerIndicator] = {}

        root = BoxLayout(orientation="vertical", padding=16, spacing=12)
        bar = BoxLayout(size_hint_y=None, height=64, spacing=8)
        back = Button(text="< Back", size_hint_x=None, width=160, font_size="20sp")
        back.bind(on_release=lambda *_: self._app.goto(ScreenName.SETTINGS))
        bar.add_widget(back)
        bar.add_widget(Label(text="Buzzer Test", font_size="24sp", bold=True))
        root.add_widget(bar)

        self._status = Label(text="Press any buzzer...", font_size="20sp", size_hint_y=None, height=48)
        root.add_widget(self._status)

        self._grid = GridLayout(cols=2, spacing=12)
        root.add_widget(self._grid)

        root.add_widget(Label(text="Assign last press to:", font_size="18sp", size_hint_y=None, height=40))
        self._assign_row = GridLayout(cols=4, size_hint_y=None, height=64, spacing=8)
        root.add_widget(self._assign_row)

        self.add_widget(root)

    def on_pre_enter(self, *_args) -> None:
        self._rebuild()
        self._app.buzzers.subscribe(self._on_event)

    def on_leave(self, *_args) -> None:
        self._app.buzzers.unsubscribe(self._on_event)

    def _rebuild(self) -> None:
        self._grid.clear_widgets()
        self._assign_row.clear_widgets()
        self._indicators.clear()
        for slot in self._app.settings.config.players:
            mapped = f" [{slot.device_id}:{slot.buzzer_index}]" if slot.is_mapped else ""
            indicator = BuzzerIndicator(text=f"{slot.name}{mapped}")
            self._indicators[slot.player_id] = indicator
            self._grid.add_widget(indicator)
            assign = Button(text=slot.name, font_size="16sp")
            assign.bind(on_release=lambda _btn, pid=slot.player_id: self._assign(pid))
            self._assign_row.add_widget(assign)

    def _on_event(self, event: BuzzerEvent) -> None:
        self._last_event = event
        self._status.text = f"Pressed: device={event.device_id} index={event.buzzer_index} button={event.button.value}"
        player_id = resolve_player_id(self._app.settings.config.players, event.device_id, event.buzzer_index)
        indicator = self._indicators.get(player_id) if player_id is not None else None
        if indicator is not None:
            indicator.flash()

    def _assign(self, player_id: int) -> None:
        event = self._last_event
        if event is None:
            self._status.text = "Press a buzzer first, then choose a player."
            return
        config = self._app.settings.config
        players = [
            replace(slot, device_id=event.device_id, buzzer_index=event.buzzer_index)
            if slot.player_id == player_id
            else slot
            for slot in config.players
        ]
        self._app.settings.update(replace(config, players=players))
        self._rebuild()
        self._status.text = f"Assigned {event.device_id}:{event.buzzer_index} to player {player_id}."
