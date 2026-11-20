# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Misheard names (Pro): the feature object the router is handed.

The AGPL router knows only a narrow contract — ``note_played(client, terms)``
after a turn that played something (``localvoice/alternatives.py``) — and
owns none of what follows. This module owns the rest: the licence gate, the
background threads, and what is read from the music system to fill the
:class:`~pro.name_index.NameIndex`. The design is
docs/name-recognition-design.md; the matching that uses the index is step 1c.

Why a play is recorded by *asking the player*, not from the reply: a reply
says what was asked for, in the words of the request — «Riproduco camin». The
player says what is actually playing, spelt the way its catalogue spells it:
«Kamin», by «EMIN & JONY». That spelling is the whole point of keeping a
history. And because the player can be a beat behind — still reporting the
previous track a moment after the new one was queued — a reading only counts
when it agrees with what the turn said it started (:func:`_vouched_for`).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterable, List, Optional

from matching import parse_song_query
from pro.name_index import NameIndex
from pro.phonetic import fold

#: How long after a turn the player is asked what it is playing: long enough
#: for a streaming track to have replaced the previous one in its status.
SETTLE_SECONDS = 2.0

#: How often favourites and library artists are read again from the music
#: system. They change when somebody saves a favourite or adds a record:
#: rarely, and never in a way that needs noticing within the hour.
REFRESH_SECONDS = 6 * 3600

#: How many favourites and library artists are read. A library bigger than
#: this keeps its first names in the music system's order; the history still
#: covers whatever is actually played.
MAX_FAVORITES = 500
MAX_LIBRARY_ARTISTS = 5000

#: How close a known name has to sound to what was heard to replace it.
#: «camin»/«Kamin» is 1.0; «emin»/«Eminem», two different artists, is 0.8 —
#: which is why this is not lower. Measured in tests/test_phonetic.py.
ACCEPT = 0.9

#: How far ahead of the runner-up the best name has to be. Two known names
#: that both sound like what was heard are a question, not an answer, and
#: the turn is left as it was.
MARGIN = 0.1

#: The word that joins a title to its artist, per language — one that
#: ``parse_song_query`` splits on (engine/connectors/), so the sentence
#: rebuilt here is read back as the title and the artist it names.
BY = {"it": "di", "en": "by", "de": "von", "fr": "par", "es": "de"}


def _in_background(fn: Callable, *args: Any) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


class Names:
    """The misheard-names feature: licence gate, play history, sources.

    ``capabilities`` is the backend's declaration (``player/protocols.py``):
    favourites and library artists are read only from a backend that says it
    has them. ``spawn`` and ``sleep`` are injectable so tests run the
    background work inline and without waiting.
    """

    def __init__(self, index: NameIndex, license_mgr, *, capabilities=None,
                 spawn: Callable[..., None] = _in_background,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 settle: float = SETTLE_SECONDS,
                 refresh_every: float = REFRESH_SECONDS) -> None:
        self.index = index
        self.license = license_mgr
        self.capabilities = capabilities
        self._spawn = spawn
        self._sleep = sleep
        self._clock = clock
        self._settle = settle
        self._refresh_every = refresh_every
        self._refreshed_at: Optional[float] = None
        self._refresh_lock = threading.Lock()

    def pro_ok(self) -> bool:
        return self.license is not None and self.license.is_pro()

    # -- the router's contract -------------------------------------------------

    def note_played(self, client, terms: Iterable[str]) -> None:
        """A turn just started something named by ``terms``. Returns at once:
        the player is asked later, in the background."""
        if not self.pro_ok():
            return
        self.refresh_if_stale(client)
        if not self.index.history_enabled:
            return
        self._spawn(self._record, client, [t for t in terms if t])

    def _record(self, client, terms: List[str]) -> None:
        self._sleep(self._settle)
        try:
            now = client.now_playing_info()
        except Exception:  # noqa: BLE001 — the player is not answering: no entry
            return
        if not now:
            return
        title, artist = now.get("title"), now.get("artist")
        if _vouched_for(terms, title, artist):
            self.index.add_played(title, artist)

    def rename(self, queries: List[str], lang: str = "it") -> Optional[dict]:
        """The first of ``queries`` that sounds like a known name, rewritten
        with that name — or None.

        ``queries`` are what each recognition alternative asked to play
        («camin», «coming di eminem e johnny»), in the recogniser's order.
        The answer is ``{"index", "text", "title", "artist"}``: which query,
        the words to put in its place («Kamin di EMIN & JONY»), and the name
        they come from. The caller runs the rewritten sentence through the
        whole router, kid-safe included; nothing is played from here.
        """
        if not self.pro_ok():
            return None
        for i, query in enumerate(queries):
            parsed = parse_song_query(query, lang=lang)
            title, artist = parsed.get("title"), parsed.get("artist")
            entry = _decide(self.index.match(title, artist, lang=lang),
                            heard_artist=bool(artist))
            if entry is None:
                continue
            text = _phrase(entry, lang, with_artist=bool(artist))
            if not text or fold(text) == fold(query):
                continue  # it would ask for exactly what was already asked
            return {"index": i, "text": text, "title": entry.get("title"),
                    "artist": entry.get("artist")}
        return None

    # -- names read from the music system ------------------------------------

    def refresh_if_stale(self, client) -> None:
        """Read favourites and library artists again if it is time, in the
        background; the first call after start-up always does."""
        now = self._clock()
        with self._refresh_lock:
            if (self._refreshed_at is not None
                    and now - self._refreshed_at < self._refresh_every):
                return
            self._refreshed_at = now
        self._spawn(self.refresh, client)

    def refresh(self, client) -> None:
        """Read the sources this backend has. One that fails keeps what it
        had: a music system restarting is not a library that emptied."""
        caps = self.capabilities
        if caps is None or getattr(caps, "favorites", False):
            try:
                items = client.favorites_items(count=MAX_FAVORITES)
            except Exception:  # noqa: BLE001
                items = None
            if items is not None:
                self.index.set_source("favorites", [
                    {"title": it.get("name") or it.get("title"), "kind": "track"}
                    for it in items if it.get("name") or it.get("title")])
        if caps is None or getattr(caps, "local_library", False):
            try:
                artists = client.local_artists(count=MAX_LIBRARY_ARTISTS)
            except Exception:  # noqa: BLE001
                artists = None
            if artists is not None:
                self.index.set_source("library", [
                    {"artist": a.get("title"), "kind": "artist"}
                    for a in artists if a.get("title")])


def _vouched_for(terms: Iterable[str], title: Optional[str],
                 artist: Optional[str]) -> bool:
    """Whether the player's reading is about what the turn started.

    One of the turn's names has to be found in the reading's title or artist,
    or the other way round: «Kamin» in «Kamin (Remix)», «EMIN» in «EMIN &
    JONY». Anything else is the player still showing the previous track, or
    something somebody else started in the meantime — and the price of
    recording that is the wrong name kept as a known one.
    """
    # Whole words, not substrings: «Time» is not «Timeless».
    reading = [set(fold(title).split()), set(fold(artist).split())]
    for term in terms:
        t = set(fold(term).split())
        if not t:
            continue
        for r in reading:
            if r and (t <= r or r <= t):
                return True
    return False


def _decide(ranked, *, heard_artist: bool) -> Optional[dict]:
    """The known name to use, from :meth:`NameIndex.match`'s ranking, or None.

    Over :data:`ACCEPT`, and :data:`MARGIN` ahead of the next *different*
    name — the same song kept twice (played, and saved as a favourite) is one
    name, not a rival. Two songs with the same title by different artists,
    when no artist was heard, are still one answer about the title: the
    search will ask which, as it would have for a title spelt right.
    """
    seen, distinct = set(), []
    for score, entry in ranked:
        key = (fold(entry.get("title")), fold(entry.get("artist")))
        if key not in seen:
            seen.add(key)
            distinct.append((score, entry))
    if not distinct or distinct[0][0] < ACCEPT:
        return None
    best_score, best = distinct[0]
    rivals = [e for s, e in distinct[1:] if s > best_score - MARGIN]
    if not rivals:
        return best
    title = fold(best.get("title"))
    if (title and not heard_artist
            and all(fold(e.get("title")) == title for e in rivals)):
        return {"title": best.get("title"), "artist": None}
    return None


def _phrase(entry: dict, lang: str, *, with_artist: bool) -> str:
    """A known name as words a request would say: «Kamin», «Kamin di EMIN &
    JONY», or the artist alone for an artist.

    The artist only when one was heard. Not every path splits it off: the
    streaming search does (``parse_song_query``), the local library searches
    the whole phrase — so «metti camin» becomes «metti Kamin», which both
    understand, and only a request that named an artist gets one back.
    """
    title, artist = entry.get("title"), entry.get("artist")
    if title and artist and with_artist:
        return f"{title} {BY.get(lang, BY['it'])} {artist}"
    return title or artist or ""
