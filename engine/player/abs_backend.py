"""Audiobookshelf, as the registry should know it.

Declared as a ``SPOKEN_LIBRARY``, not a ``BACKEND``: there is no player in
Audiobookshelf to aim at, so it is named by ``--library`` beside whichever
music system is playing (see :class:`~player.registry.Library`). Its own file
for the reason ``ma_backend`` gives — declaring a library is not client work.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .audiobookshelf import AudiobookshelfClient
from .protocols import Capabilities
from .registry import Library


def build(url: str, *, token: Optional[str] = None,
          timeout: float = 8.0) -> AudiobookshelfClient:
    """A client for one Audiobookshelf server. Dials nothing."""
    return AudiobookshelfClient(url, token=token or "", timeout=timeout)


def probe(url: str, *, token: Optional[str] = None,
          timeout: float = 3.0) -> List[Dict[str, Any]]:
    """The book libraries this key can see. Raises if the server is not there
    or refuses the key."""
    return AudiobookshelfClient(url, token=token or "",
                                timeout=timeout).book_libraries()


SPOKEN_LIBRARY = Library(
    name="audiobookshelf",
    label="Audiobookshelf",
    # Not ``search``: that flag promises the music catalogue — albums,
    # artists, playlists — and a shelf of books claiming it is the partial
    # library the protocol tests exist to refuse.
    capabilities=Capabilities(streamable=True),
    build=build,
    probe=probe,
)
