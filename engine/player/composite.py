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

import time

from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import PlayerError
from .book_position import (CHAPTER_SLACK, LENGTH_TOLERANCE, chapter_point,
                            file_chapters, file_titles, resume_point, seconds,
                            seek_landed)
from .book_listening import Listening, _from_library, _player_key
from .protocols import Capabilities, supports

#: How the engine's three enqueue modes are spelled, as elsewhere
#: (``actions.play_song``, ``musicassistant._QUEUE_OPTION``).
MODES = ("play", "add", "insert")


class Composite(Listening):
    """A :class:`~player.protocols.SpokenLibrary`, heard through any transport."""

    def __init__(self, library: Any, capabilities: Capabilities,
                 label: str = "", *, now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
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
        self._now, self._sleep = now, sleep  # the seek check's, injectable
        # What each player was last given, as ``player_id -> (item_id,
        # first, count)``: the book, the index of its file now at the head
        # of the queue, and how many of its files follow. Written by every
        # ``play``, dropped by ``add``/``insert`` (the book is then behind
        # something else, at a place that depends on what) — and the only
        # way to know where a book is, because a transport says *which queue
        # position* is playing, never which URL (T5.6, chapters).
        #
        # Here and not on the Router: there is one router per browser, and a
        # book started from the phone must still move for «capitolo
        # successivo» said to the satellite in the same room. Plain dict
        # writes of whole tuples, which the GIL keeps whole across the
        # server's threads.
        self._playing: Dict[Any, Tuple[str, int, int]] = {}
        # Beside each record: the transport it was played on, which is how
        # the progress sampler (localvoice/book_progress.py) reaches a player
        # it has no request for; and the last position saved, with the record
        # it belonged to, so a book started over is saved again at once.
        self._transports: Dict[Any, Any] = {}
        # Each book a record points at, as the catalogue's ``book()`` answers
        # it — files, chapters, title, author — read the first time it is
        # needed and again only when the book is played again. The page
        # polls every few seconds, and a request per poll per player for
        # files the catalogue already sent is what this saves.
        self._books: Dict[str, Dict[str, Any]] = {}
        self._saved: Dict[Any, Tuple[Tuple[str, int, int], float]] = {}

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
        book = self._read_book(item_id) if mode == "play" else None
        urls = ([f["url"] for f in book["tracks"]] if book is not None
                else _from_library(self.library.stream_urls, item_id))
        if not urls:
            return 0
        key = _player_key(transport)
        if mode == "play":
            # One call, the one the protocol has for exactly this: Music
            # Assistant takes the whole list at once, and a play_url followed
            # by add_url per chapter would race the first file starting.
            transport.play_tracks(_queued(urls, book))
            self._remember(transport, (item_id, 0, len(urls)),
                           fresh=book is not None)
            return len(urls)
        self._playing.pop(key, None)
        if mode == "add":
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
        files, book = self._files(item_id)
        return self._play_files(transport, item_id, files, start, book)

    def _play_files(self, transport: Any, item_id: str,
                    files: List[Dict[str, Any]], start: float,
                    book: Optional[Dict[str, Any]] = None) -> Tuple[int, float]:
        """:meth:`play_from`, once the files are in hand — and the book they
        came from, when it was read whole (titles for the queue)."""
        if not files:
            return 0, 0.0
        urls = [f["url"] for f in files]
        point = resume_point(files, start)
        index, offset = point if point is not None else (0, 0.0)
        # Not ours to sample until the seek is done: in between, the new
        # file plays from 0 s, and a save there would write that over the
        # resume point — through the old record, too, if this player had one.
        key = _player_key(transport)
        self._playing.pop(key, None)
        transport.play_tracks(_queued(urls, book)[index:])
        reached = start - offset if point is not None else 0.0
        landed = True
        if offset > 0 and supports(transport, "seek"):
            # The book is already playing: a seek that fails costs the
            # second, not the book, and the answer stays the file's start.
            try:
                transport.seek(int(offset))
                landed = self._landed(transport, int(offset))
            except PlayerError:
                landed = False
            if landed:
                reached += int(offset)
        if landed:
            # A seek that did not land leaves the file playing from 0 s, and
            # a save from there would write it over the resume point the
            # catalogue kept — hours of it, on a one-file .m4b. Not ours, then:
            # no chapter is named for it and nothing is saved.
            self._remember(transport, (item_id, index, len(urls) - index),
                           fresh=book is not None)
        return len(urls) - index, reached

    def _landed(self, transport: Any, target: int) -> bool:
        """Whether ``transport`` really got to ``target`` seconds after a seek
        it accepted — see :func:`book_position.seek_landed`. A player that
        cannot say where it is is trusted: there is nothing to check against."""
        now_playing = getattr(transport, "now_playing_info", None)
        if now_playing is None:
            return True
        return seek_landed(lambda: (now_playing() or {}).get("elapsed"),
                           target, self._now, self._sleep)

    # -- chapters (T5.6) -----------------------------------------------------
    def chapter_at(self, transport: Any) -> Optional[Dict[str, Any]]:
        """Where ``transport`` is in the book this composite last gave it:
        ``{"item_id", "chapters", "index"}`` — the chapter list and the one
        playing — or ``None`` when that player is not playing a book of ours.

        "Not playing a book of ours" is decided with some care, because the
        answer moves a book or names a chapter aloud: nothing was given to
        this player, the player is stopped, the queue has moved past the
        book, or the file at the head is not as long as the book's file
        there. The last is the one that catches a record put on from
        Material Skin since — same player, same index, playing — and on it
        the record is dropped, so a coincidence later cannot bring the book
        back. A player that reports no length is trusted (the check is
        skipped, not failed).

        The chapters are the catalogue's (``chapters()``, probed with
        ``getattr`` as ``tracks`` is), placed by the seconds into the whole
        book — which a file of unknown length before the head makes
        unknowable, and is ``None`` too. When the catalogue has none, each
        file is one chapter — the folder-of-MP3s shape — and the file
        playing is the chapter, with no arithmetic at all; a file whose
        start cannot be summed has ``"start": None`` and can be named but
        not jumped to (:meth:`play_chapter`).
        """
        found = self._locate(transport)
        if found is None:
            return None
        (item_id, _, _), durations, head, elapsed = found
        chapters = self._books[item_id]["chapters"]
        if not chapters:
            return {"item_id": item_id, "chapters": file_chapters(durations),
                    "index": head}
        if not all(durations[:head]):
            return None
        position = sum(durations[:head]) + elapsed
        current = max((i for i, ch in enumerate(chapters)
                       if ch["start"] <= position + CHAPTER_SLACK), default=0)
        return {"item_id": item_id, "chapters": chapters, "index": current}

    def play_chapter(self, transport: Any, item_id: str,
                     chapter: Dict[str, Any]) -> Optional[float]:
        """Play ``item_id`` from the start of ``chapter`` — the resume path,
        from a point the listener named rather than one Audiobookshelf kept.

        Answers where playback really begins (as :meth:`play_from`), or
        ``None``, **with nothing sent**, when the chapter starts inside a
        file and ``transport`` cannot seek: the file from its own start
        would be an earlier chapter announced as this one.

        Raises :class:`ValueError`, also with nothing sent, when the book's
        files cannot place the chapter at all — its start unknown, a file of
        unknown length before it, or a start past the end of the files.
        That is not the player's fault, and the caller says so differently.
        """
        start = chapter.get("start")
        if start is None:
            raise ValueError("chapter start unknown")
        start = seconds(start)
        get_tracks = getattr(self.library, "tracks", None)
        if start <= 0 or get_tracks is None:
            return self.play_from(transport, item_id, start)[1]
        files, book = self._files(item_id)
        point = chapter_point(files, start)
        if point is None:
            raise ValueError(f"chapter at {start}s is not inside the files")
        index, offset = point
        if offset > 0 and not supports(transport, "seek"):
            return None
        placed = sum(f.get("duration") or 0.0 for f in files[:index]) + offset
        return self._play_files(transport, item_id, files, placed, book)[1]

    def _remember(self, transport: Any, record: Tuple[str, int, int],
                  fresh: bool = False) -> None:
        key = _player_key(transport)
        self._playing[key] = record
        self._transports[key] = transport
        # Played again: read again (a chapter edited in the catalogue shows up
        # at the next play) — unless it was read to queue it, just now. And
        # nothing kept for a book no player holds.
        if not fresh:
            self._books.pop(record[0], None)
        held = {item for item, _, _ in self._playing.values()}
        for item in [item for item in self._books if item not in held]:
            self._books.pop(item, None)

    def _read_book(self, item_id: str) -> Optional[Dict[str, Any]]:
        """The book read afresh from a catalogue that has ``book()``, kept for
        the page and the chapters; ``None`` from one that does not."""
        get_book = getattr(self.library, "book", None)
        if get_book is None:
            return None
        book = _from_library(get_book, item_id)
        self._books[item_id] = book
        return book

    def _files(self, item_id: str) -> Tuple[List[Dict[str, Any]],
                                             Optional[Dict[str, Any]]]:
        """A book's files, with their lengths, read afresh to play them; and
        the whole book when the catalogue answers one (``None`` otherwise)."""
        book = self._read_book(item_id)
        if book is not None:
            return book["tracks"], book
        return _from_library(self.library.tracks, item_id), None

    def _book(self, item_id: str) -> Optional[Dict[str, Any]]:
        """``{"title", "author", "tracks", "chapters"}`` for ``item_id``, from
        memory when it is there. A catalogue with a ``book()`` answers it in
        one call; one with only ``tracks`` (and maybe ``chapters``) is asked
        those, and has no title to show; one with neither, ``None``."""
        book = self._books.get(item_id)
        if book is not None:
            return book
        get_book = getattr(self.library, "book", None)
        get_tracks = getattr(self.library, "tracks", None)
        if get_book is not None:
            book = _from_library(get_book, item_id)
        elif get_tracks is not None:
            get_chapters = getattr(self.library, "chapters", None)
            book = {"title": "", "author": "",
                    "tracks": _from_library(get_tracks, item_id),
                    "chapters": (_from_library(get_chapters, item_id)
                                 if get_chapters else [])}
        else:
            return None
        self._books[item_id] = book
        return book

    def _locate(self, transport: Any) -> Optional[tuple]:
        """``(record, durations, head, elapsed)`` for the book of ours
        ``transport`` is playing — the file at the head of its queue and the
        seconds played of it — or ``None``; see :meth:`chapter_at` for what
        "of ours" takes."""
        key = _player_key(transport)
        record = self._playing.get(key)
        if record is None:
            return None
        item_id, first, count = record
        now = transport.now_playing_info() or {}
        index = now.get("index")
        if (now.get("mode") not in ("play", "pause")
                or not isinstance(index, int) or not 0 <= index < count):
            return None
        book = self._book(item_id)
        if book is None:
            return None
        files = book["tracks"]
        head = first + index
        durations = [f.get("duration") or 0.0 for f in files]
        heard = seconds((transport.status_info() or {}).get("duration"))
        if head >= len(files) or (heard and durations[head] and
                                  abs(heard - durations[head]) > LENGTH_TOLERANCE):
            self._forget(key, record)
            return None
        return record, durations, head, seconds(now.get("elapsed"))

    def _forget(self, key: Any, record: Tuple[str, int, int]) -> None:
        """Drop ``record`` — only if it is still the one there. Between
        reading it and finding it stale, :meth:`chapter_at` has asked the
        network, and a book started meanwhile from another thread is a new
        record this must not delete."""
        if self._playing.get(key) is record:
            self._playing.pop(key, None)
            self._saved.pop(key, None)


def _queued(urls: List[str], book: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The entries ``play_tracks`` takes: each URL, with the title the queue
    should show before the file has played when the book is known (see
    ``book_position.file_titles``)."""
    titles = file_titles(book) if book is not None else [None] * len(urls)
    return [dict({"url": url}, **({"queue_title": title} if title else {}))
            for url, title in zip(urls, titles)]
