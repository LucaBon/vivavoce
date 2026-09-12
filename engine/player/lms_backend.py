"""Lyrion/Logitech Media Server, as a backend among others.

There is almost nothing here, and that is the point. ``LMSClient`` already had
every method :mod:`player.protocols` asks for — it is where the protocols were
read off — so this module does not wrap it, adapt it or rename anything. It
says what LMS is called, what it can do, and how to build one.

The LMS has no access token: it is a machine on the household LAN, optionally
behind HTTP Basic auth. ``build`` accepts ``token`` because the registry hands
the same arguments to every backend, and ignores it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import discovery
from lms import LMSClient

from .protocols import Capabilities
from .registry import Backend

#: The player id used to ask an LMS what players it has before one has been
#: chosen. Any id answers a server-wide query; "0" is what the setup page has
#: always sent.
PROBE_PLAYER_ID = "0"


def build(url: str, player_id: str, *, token: Optional[str] = None,
          timeout: float = 8.0) -> LMSClient:
    """A client aimed at one player of one LMS. ``token`` is not used."""
    return LMSClient(url, player_id, timeout=timeout)


def probe(url: str, *, token: Optional[str] = None,
          timeout: float = 3.0) -> List[Dict[str, Any]]:
    """The players this LMS knows. Raises ``LMSError`` if it is not there."""
    return LMSClient(url, PROBE_PLAYER_ID, timeout=timeout).get_players()


def discover(*, on_progress=None, timeout: float = 2.0) -> Optional[str]:
    """The first LMS answering on the LAN, by UDP broadcast on port 3483."""
    return discovery.discover_base_url(timeout=timeout, on_progress=on_progress)


BACKEND = Backend(
    name="lms",
    label="Lyrion Music Server",
    # LMS is the system every one of these was written against, so it does all
    # of it: three streaming services behind one server, a local library
    # indexed by artist/album/genre/year, favourites, and a sleep timer of its
    # own. A backend that does less says so, and the engine offers less.
    capabilities=Capabilities(
        search=True, local_library=True, favorites=True, genres=True,
        years=True, browse_items=True, services=True, sleep_timer=True,
        seek=True, multi_player=True, artwork=True,
    ),
    build=build,
    probe=probe,
    discover=discover,
)
