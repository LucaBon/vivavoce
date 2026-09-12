"""The player layer: what Vivavoce needs from a music system, and who provides it.

Vivavoce used to be able to drive exactly one thing, a Lyrion/LMS, because the
client that talked to it *was* the interface. Nothing about picking the right
record for a spoken sentence depends on who plays it, though, so this package
separates the two: :mod:`protocols` says what the engine needs, and a backend
module says how one particular system provides it.

Read :mod:`protocols` first — the split between a device and a catalogue is
the whole design, and the rest follows from it.
"""

from __future__ import annotations

from .errors import PlayerError
from .protocols import Capabilities, MusicLibrary, PlayerTransport
from .resilience import BREAKER_COOLDOWN, BREAKER_THRESHOLD, Breaker, Resilient

__all__ = [
    "BREAKER_COOLDOWN",
    "BREAKER_THRESHOLD",
    "Breaker",
    "Capabilities",
    "MusicLibrary",
    "PlayerError",
    "PlayerTransport",
    "Resilient",
]
