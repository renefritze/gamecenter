"""The service contract for long-lived features (future: webcam, Spotify).

Services mirror the game plugin pattern so future features (a USB webcam feed,
Spotify playback control) drop into :class:`~gamecenter.core.registry.ServiceRegistry`
and reach games via :class:`~gamecenter.core.game_api.GameContext` without any
launcher or game rework. No concrete services ship yet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class Service(ABC):
    """A long-lived feature started with the app and shared with games."""

    id: ClassVar[str]

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Whether this service can run in the current environment."""

    @abstractmethod
    def start(self) -> None:
        """Start the service."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the service and release resources."""
