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
from pro.corrections import Corrections
from pro.name_index import NameIndex
from pro.naming import ACCEPT, BY, MARGIN, _decide, _phrase  # noqa: F401
from pro.phonetic import fold, phonetic_score
from pro.spelling import respell

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

#: How alike what was said and what was then written must be for the page to
#: offer "remember this". Low on purpose, measured on real cases: «sfigati»
#: for «Audioslave» — a mishearing this repository has on record — is 0.24,
#: «coming di eminem e johnny» for «Kamin di EMIN & JONY» 0.83, while
#: somebody changing their mind («vasco», then «i Queen») is 0.18. A chip
#: offered in error is ignored at no cost; nothing is kept without a tap.
SUGGEST = 0.2

#: How much of the history is handed to Whisper as names to expect (phase 3).
#: faster-whisper trims what it is given to half its 448-token context; at
#: about three characters a token, 600 characters stays inside that with room
#: to spare, so nothing is cut mid-name by the engine.
MAX_HOTWORDS_CHARS = 600


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
                 corrections: Optional[Corrections] = None,
                 spawn: Callable[..., None] = _in_background,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 settle: float = SETTLE_SECONDS,
                 refresh_every: float = REFRESH_SECONDS) -> None:
        self.index = index
        self.corrections = corrections
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

    def respell(self, queries: List[str], lang: str = "it", *,
                search: Callable[[str], list]) -> Optional[dict]:
        """For a name the household has never played: the first of
        ``queries`` whose respelling the catalogue holds, answered like
        :meth:`rename` — or None. Phase 4; see :func:`pro.spelling.respell`.
        """
        if not self.pro_ok():
            return None
        return respell(queries, lang, search)

    def hotwords(self, lang: str = "it") -> Optional[str]:
        """The names Whisper should expect, as one string — or None.

        What the household confirmed it means first (the «meant» of its
        corrections in ``lang``), then the most played titles and artists,
        each name once, until :data:`MAX_HOTWORDS_CHARS`. Favourites and
        library artists are left out: a library of five thousand artists is
        not a hint, it is noise, and Whisper would start hearing them.
        """
        if not self.pro_ok():
            return None
        names: List[str] = []
        if self.corrections is not None:
            for c in self.corrections.items():
                if c.get("lang", "it") == lang:
                    parsed = parse_song_query(c["meant"], lang=lang)
                    names += [parsed.get("title"), parsed.get("artist")]
        for entry in self.index.history():
            names += [entry.get("title"), entry.get("artist")]
        seen, kept, size = set(), [], 0
        for name in names:
            key = fold(name)
            if not key or key in seen:
                continue
            if size + len(name) + 2 > MAX_HOTWORDS_CHARS:
                break
            seen.add(key)
            kept.append(name.strip())
            size += len(name) + 2
        return ", ".join(kept) or None

    # -- corrections the household confirmed (phase 2) ----------------------

    def correct(self, queries: List[str], lang: str = "it") -> Optional[dict]:
        """The first of ``queries`` somebody confirmed a correction for, as
        ``{"index", "text"}`` — or None. Applied before the turn is routed:
        a confirmed rule outranks whatever the search would make of the
        words, including a search that would have played something."""
        if not self.pro_ok() or self.corrections is None:
            return None
        for i, query in enumerate(queries):
            hit = self.corrections.lookup(query, lang)
            if hit:
                return {"index": i, "text": hit["meant"]}
        return None

    def suggest(self, heard: List[str], meant: str,
                lang: str = "it") -> Optional[dict]:
        """``{"heard", "meant"}`` to offer as "remember this", or None.

        ``heard`` is what a spoken turn asked to play (every alternative),
        ``meant`` what was then written and played. Offered only when the two
        are alike enough to be the same request (:data:`SUGGEST`), differ in
        their letters, and are not already a rule.
        """
        if not self.pro_ok() or self.corrections is None:
            return None
        meant = (meant or "").strip()
        best, best_score = None, 0.0
        for h in heard:
            h = (h or "").strip()
            if not fold(h) or fold(h) == fold(meant):
                continue
            score = phonetic_score(h, meant, lang)
            if score > best_score:
                best, best_score = h, score
        if best is None or best_score < SUGGEST:
            return None
        known = self.corrections.items()
        if any(fold(c["heard"]) == fold(best) and fold(c["meant"]) == fold(meant)
               for c in known):
            return None
        return {"heard": best, "meant": meant}

    # -- the settings page ---------------------------------------------------

    def state(self) -> dict:
        """What the settings section shows (``GET /names``)."""
        history = self.index.history()
        return {"pro": self.pro_ok(),
                "history_enabled": self.index.history_enabled,
                "history_count": len(history),
                "history": [{"title": e.get("title"), "artist": e.get("artist"),
                             "plays": e.get("weight")} for e in history[:20]],
                "corrections": [
                    {"id": c["id"], "heard": c["heard"], "meant": c["meant"],
                     "lang": c.get("lang", "it")}
                    for c in (self.corrections.items() if self.corrections else [])]}

    def act(self, payload: dict) -> dict:
        """One change from the settings page or a "remember" tap
        (``POST /names``). Always answers with the new state."""
        if not self.pro_ok():
            return {"ok": False, "error": "pro_required", **self.state()}
        action = payload.get("action")
        ok = True
        if action == "history":
            self.index.set_history_enabled(payload.get("enabled") is True)
        elif action == "clear_history":
            self.index.clear_history()
        elif action == "forget" and self.corrections is not None:
            ok = self.corrections.forget(str(payload.get("id") or ""))
        elif action == "remember" and self.corrections is not None:
            heard, meant = payload.get("heard"), payload.get("meant")
            lang = payload.get("lang")
            ok = (isinstance(heard, str) and isinstance(meant, str)
                  and self.corrections.add(
                      heard, meant, lang if isinstance(lang, str) else "it")
                  is not None)
        else:
            return {"ok": False, "error": "unknown_action", **self.state()}
        return {"ok": bool(ok), **self.state()}

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

