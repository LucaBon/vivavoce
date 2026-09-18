"""MusicAssistant, as a backend among others.

The twin of :mod:`player.lms_backend`, and as thin as that one: what this
system is called, what it can do, and how to build one.
:class:`~player.musicassistant.MusicAssistantClient` already answers every
method :mod:`player.protocols` asks for, so nothing here wraps it, adapts it
or renames anything.

Its own file because declaring a backend is not client work — over there is
what a MusicAssistant client *does*, here is what the registry should know
about it — and because that client had grown to the 400-line ceiling with this
still inside it. The registry finds it either way: ``registry._load`` imports
every module in this package and looks for ``BACKEND``, rather than knowing
where anyone put it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .ma_transport import DEFAULT_PORT
from .musicassistant import MusicAssistantClient
from .protocols import Capabilities
from .registry import Backend


def build(url: str, player_id: str, *, token: Optional[str] = None,
          timeout: float = 8.0) -> MusicAssistantClient:
    """A client aimed at one player of one MusicAssistant server."""
    return MusicAssistantClient(url, player_id, token=token or "",
                                timeout=timeout)


def probe(url: str, *, token: Optional[str] = None,
          timeout: float = 3.0) -> List[Dict[str, Any]]:
    """The players this server knows. Raises if it is not there."""
    return MusicAssistantClient(url, "probe", token=token or "",
                                timeout=timeout).get_players()


BACKEND = Backend(
    name="musicassistant",
    label=MusicAssistantClient.SYSTEM_LABEL,  # see lms_backend.py
    capabilities=Capabilities(
        search=True, local_library=True, favorites=True, genres=True,
        browse_items=True, services=True, sleep_timer=True, seek=True,
        multi_player=True, artwork=True,
        # No year index: MusicAssistant has no equivalent of the LMS "years"
        # listing, so the mood that picks a decade falls through to a
        # streaming playlist instead of loading the library by year.
        years=False,
    ),
    build=build,
    probe=probe,
    default_port=DEFAULT_PORT,
    # Nothing to broadcast to: MusicAssistant announces itself over mDNS, not
    # over a protocol this project already speaks, so it has to be told where
    # it is. That is a fact about the server, not a gap in this backend.
    discover=None,
)
