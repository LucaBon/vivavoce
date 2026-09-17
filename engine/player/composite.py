"""A catalogue from one place, played through the speakers of another.

The household already has something that plays — an LMS, a MusicAssistant —
and Audiobookshelf adds books, not a hi-fi. So "play this book" is two
systems' work: the catalogue turns an id into files, the transport plays
them. This module is the handshake between the two, and nothing more.

**Why the transport is an argument and not a field.** The obvious shape is a
wrapper that *is* the music client with a bookshelf bolted on, handed to the
engine in its place. It would have to re-wrap everything that hands back a
client — ``for_player``, ``for_service`` — or a room turn would quietly drop
the books, and a shallow copy somewhere down the line would drop them again.
Here nothing is wrapped: the caller passes whichever transport it is holding
at that moment, so «continua il libro in cucina» plays in the kitchen for the
same reason «metti Time in cucina» does, with no code of its own. And with no
``--library`` there is no :class:`Composite` at all, which is how a household
without books is guaranteed to notice nothing.

The engine never names the catalogue: it asks :class:`Capabilities`, as
everywhere else.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .protocols import Capabilities

#: How the engine's three enqueue modes are spelled, as elsewhere
#: (``actions.play_song``, ``musicassistant._QUEUE_OPTION``).
MODES = ("play", "add", "insert")


class Composite:
    """A :class:`~player.protocols.SpokenLibrary`, heard through any transport."""

    def __init__(self, library: Any, capabilities: Capabilities,
                 label: str = "") -> None:
        # Refused here, at startup, rather than at the first sentence: a
        # catalogue that cannot say where its files are would be offered to
        # the listener and then fail every request, which is the "declared
        # and not kept" failure the Capabilities table exists to prevent.
        if not capabilities.streamable:
            raise ValueError(
                f"{label or 'this library'} cannot hand its files to another "
                f"system's speakers (not streamable)")
        self.library = library
        self.capabilities = capabilities
        self.label = label

    def book_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        return self.library.book_candidates(query, count)

    def enqueue(self, transport: Any, item_id: str, mode: str = "play") -> int:
        """Put one book's files on ``transport``'s queue, in listening order.

        ``play`` replaces the queue and starts at the first file, ``add``
        appends, ``insert`` goes in right after what is playing. Answers how
        many files were queued; ``0`` means the catalogue had nothing to
        listen to and **nothing was sent** — the queue a listener had is not
        cleared for a book that turned out to be an e-book.

        ``insert`` walks the files backwards. Each ``insert_url`` lands
        directly after the current track, ahead of the one inserted before
        it, so inserting chapter 1 then chapter 2 would queue 2 before 1.
        """
        if mode not in MODES:
            raise ValueError(f"unknown enqueue mode {mode!r}")
        urls = self.library.stream_urls(item_id)
        if not urls:
            return 0
        if mode == "play":
            # One call, the one the protocol has for exactly this: Music
            # Assistant takes the whole list at once, and a play_url followed
            # by add_url per chapter would race the first file starting.
            transport.play_tracks([{"url": url} for url in urls])
        elif mode == "add":
            for url in urls:
                transport.add_url(url)
        else:
            for url in reversed(urls):
                transport.insert_url(url)
        return len(urls)
