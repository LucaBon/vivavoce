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
