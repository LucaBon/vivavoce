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

from typing import Any, Dict, List, Optional, Tuple

from .errors import PlayerError
from .protocols import Capabilities, supports

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

    def progress(self, item_id: str) -> Optional[float]:
        """How far into ``item_id`` the last listener got, in seconds — or
        ``None`` when the catalogue has no notion of progress at all (probed
        with ``getattr``, for the same reason as ``play_from``'s ``tracks``) or
        never started this book."""
        get_progress = getattr(self.library, "progress", None)
        return get_progress(item_id) if get_progress is not None else None

    def enqueue(self, transport: Any, item_id: str, mode: str = "play",
                start: float = 0.0) -> int:
        """Put one book's files on ``transport``'s queue, in listening order.

        ``play`` replaces the queue and starts at the first file, ``add``
        appends, ``insert`` goes in right after what is playing. Answers how
        many files were queued; ``0`` means the catalogue had nothing to
        listen to and **nothing was sent** — the queue a listener had is not
        cleared for a book that turned out to be an e-book.

        ``insert`` walks the files backwards. Each ``insert_url`` lands
        directly after the current track, ahead of the one inserted before
        it, so inserting chapter 1 then chapter 2 would queue 2 before 1.

        ``start`` is a resume point in seconds from the beginning of the
        book, honoured by ``play`` alone — see :meth:`play_from`.
        """
        if mode not in MODES:
            raise ValueError(f"unknown enqueue mode {mode!r}")
        if mode == "play" and start > 0:
            return self.play_from(transport, item_id, start)[0]
        urls = _from_library(self.library.stream_urls, item_id)
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

    def play_from(self, transport: Any, item_id: str,
                  start: float) -> Tuple[int, float]:
        """Play one book from ``start`` seconds in (T5.6). Answers how many
        files were queued and how far into the book playback **actually**
        begins — which is what the reply must say, and not always ``start``.

        Placing ``start`` needs the length of every file before it, so it is
        only acted on when the catalogue can say how long each file runs
        (:meth:`~player.audiobookshelf.AudiobookshelfClient.tracks`, probed
        with ``getattr`` because :class:`~player.protocols.SpokenLibrary`
        does not require it). The files before the one ``start`` falls in
        are left off the queue, and the transport is asked to :meth:`seek`
        into the one that remains when it declares
        :attr:`~player.protocols.Capabilities.seek`; one that cannot still
        gets the right file, and the answer is where that file begins.
        No ``tracks``, or a duration the catalogue does not know, and the
        book plays from the beginning rather than guess: the answer is 0.
        """
        get_tracks = getattr(self.library, "tracks", None)
        if start <= 0 or get_tracks is None:
            return self.enqueue(transport, item_id, "play"), 0.0
        files = _from_library(get_tracks, item_id)
        if not files:
            return 0, 0.0
        urls = [f["url"] for f in files]
        point = _resume_point(files, start)
        index, offset = point if point is not None else (0, 0.0)
        transport.play_tracks([{"url": url} for url in urls[index:]])
        reached = start - offset if point is not None else 0.0
        if offset > 0 and supports(transport, "seek"):
            # The book is already playing: a seek that fails costs the
            # second, not the book, and the answer stays the file's start.
            try:
                transport.seek(int(offset))
                reached += int(offset)
            except PlayerError:
                pass
        return len(urls) - index, reached


def _from_library(fetch, item_id: str) -> Any:
    """``fetch(item_id)``, a call to the catalogue, with any
    :class:`PlayerError` tagged ``from_library`` so a caller can still tell
    "the catalogue's own files are unreachable" from "the speakers playing
    them are" — the two get different replies (see
    ``intents_spoken._start_book``)."""
    try:
        return fetch(item_id)
    except PlayerError as exc:
        exc.from_library = True
        raise


def _resume_point(files: List[Dict[str, Any]],
                  start: float) -> Optional[tuple]:
    """``(index, offset)`` of the file ``start`` seconds in falls inside, or
    ``None`` when a file's duration is unknown (``0.0``) and the search
    cannot be trusted past it — or when ``start`` lies past the end of a
    book whose every length is known: progress saved against other files,
    and seeking past the last one would play nothing at all."""
    elapsed = 0.0
    for index, f in enumerate(files):
        duration = f.get("duration") or 0.0
        if not duration and index < len(files) - 1:
            return None
        if start < elapsed + duration:
            return index, start - elapsed
        if index == len(files) - 1:
            return (index, start - elapsed) if not duration else None
        elapsed += duration
    return None
