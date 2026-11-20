# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""The names this household's music really has, spelt the way they are spelt.

A recogniser that writes «camin» cannot be corrected by rules alone: «camin»
is a real word in two languages, and nothing in it says the user meant a song
called «Kamin». What says so is that «Kamin» is a name this house has played,
saved or owns. This is the list of those names (docs/name-recognition-design.md
§1.2), and the one question it answers: *which known name sounds most like
what was heard?* (:meth:`NameIndex.match`).

Where the names come from:

* ``history`` — what Vivavoce itself has played, as the player reported it.
  The only source that covers the streaming services, and the most useful:
  what was played once is what gets asked for again. Persisted, capped, and
  switchable off by the household (it is on by default, §5.4).
* ``favorites``, ``library`` — read from the music system by
  :mod:`pro.names` and kept in memory only: the music system already stores
  them, and a copy on disk would only be a stale one.

Pure bookkeeping: no network, no threads, no licence. Those live in
:mod:`pro.names`, which owns the feature; this module is what it keeps.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import appdata
from pro.phonetic import fold, phonetic_score

#: How many played names are kept. Past it, the least played and least
#: recent go first: a song asked for twice a week outlives one played once
#: a year ago, whichever is newer.
MAX_HISTORY = 2000

#: What one entry looks like. ``kind`` is ``track`` (a title, maybe with its
#: artist) or ``artist`` (an artist alone); ``weight`` counts plays.
Entry = Dict[str, Any]


class NameIndex:
    """Known names: the persisted play history plus what was read from the
    music system. Thread-safe: plays are recorded from background threads
    while turns read it."""

    def __init__(self, path: str, *, clock: Callable[[], float] = time.time,
                 max_history: int = MAX_HISTORY) -> None:
        self.path = path
        self._clock = clock
        self._max_history = max_history
        self._lock = threading.RLock()
        state = appdata.read_json(path, {}) or {}
        if not isinstance(state, dict):
            state = {}
        self._history_on = state.get("history_enabled", True) is not False
        self._history: List[Entry] = [
            e for e in (state.get("history") or [])
            if isinstance(e, dict) and (e.get("title") or e.get("artist"))]
        self._sources: Dict[str, List[Entry]] = {}

    # -- the history and its switch ------------------------------------------

    @property
    def history_enabled(self) -> bool:
        return self._history_on

    def set_history_enabled(self, on: bool) -> None:
        """Switch the history on or off. Off keeps nothing new and forgets
        nothing already kept: emptying it is :meth:`clear_history`, a
        separate decision the household takes on its own."""
        with self._lock:
            self._history_on = bool(on)
            self._save()

    def clear_history(self) -> None:
        with self._lock:
            self._history = []
            self._save()

    def add_played(self, title: Optional[str], artist: Optional[str]) -> bool:
        """Count one play of ``title`` by ``artist``. False when nothing was
        kept: the history is off, or there was no name to keep."""
        title, artist = (title or "").strip() or None, (artist or "").strip() or None
        if not (title or artist):
            return False
        with self._lock:
            if not self._history_on:
                return False
            key = (fold(title), fold(artist))
            now = self._clock()
            for entry in self._history:
                if (fold(entry.get("title")), fold(entry.get("artist"))) == key:
                    entry["weight"] = int(entry.get("weight") or 0) + 1
                    entry["last"] = now
                    # The spelling the player reported last wins: a catalogue
                    # that fixed its capitalisation should not be overruled by
                    # what it said a year ago.
                    entry["title"], entry["artist"] = title, artist
                    break
            else:
                self._history.append({"title": title, "artist": artist,
                                      "kind": "track" if title else "artist",
                                      "source": "history", "weight": 1,
                                      "last": now})
                if len(self._history) > self._max_history:
                    self._history.sort(key=lambda e: (-int(e.get("weight") or 0),
                                                      -float(e.get("last") or 0)))
                    del self._history[self._max_history:]
            self._save()
            return True

    def history(self) -> List[Entry]:
        """The kept plays, most played first — for the settings page."""
        with self._lock:
            return sorted((dict(e) for e in self._history),
                          key=lambda e: (-int(e.get("weight") or 0),
                                         -float(e.get("last") or 0)))

    # -- names read from the music system ------------------------------------

    def set_source(self, source: str, entries: List[Entry]) -> None:
        """Replace everything ``source`` contributed with ``entries``. In
        memory only: the music system is where these live."""
        kept = [dict(e, source=source, weight=int(e.get("weight") or 0))
                for e in entries if e.get("title") or e.get("artist")]
        with self._lock:
            self._sources[source] = kept

    def entries(self) -> List[Entry]:
        with self._lock:
            out = list(self._history)
            for entries in self._sources.values():
                out.extend(entries)
            return [dict(e) for e in out]

    # -- the one question ------------------------------------------------------

    def match(self, title: Optional[str], artist: Optional[str] = None, *,
              lang: str = "it", limit: int = 5) -> List[Tuple[float, Entry]]:
        """Known names nearest to what was heard, best first, as
        ``[(score, entry)]`` with ``score`` in 0..1.

        ``title``/``artist`` are what the request was split into
        (``parse_song_query``). A track entry is scored on its title, and on
        its artist too when one was heard; an artist entry on whichever part
        could be naming it. Ties go to the more played name.

        A ranking, never a verdict: «emin» sits at 0.8 from «Eminem», so the
        caller decides with a threshold and a margin over the runner-up.
        """
        title = (title or "").strip()
        artist = (artist or "").strip()
        if not (title or artist):
            return []
        scored = []
        for entry in self.entries():
            score = _entry_score(entry, title, artist, lang)
            if score > 0:
                scored.append((score, int(entry.get("weight") or 0), entry))
        scored.sort(key=lambda s: (-s[0], -s[1]))
        return [(score, entry) for score, _w, entry in scored[:limit]]

    # -- persistence -------------------------------------------------------------

    def _save(self) -> None:
        # Best effort, unlike the blocklist: a history entry that did not
        # reach the disk costs one name next time, and a full disk must not
        # turn into a failed turn.
        try:
            appdata.atomic_write_json(self.path, {
                "history_enabled": self._history_on,
                "history": self._history})
        except OSError:
            pass


def _entry_score(entry: Entry, title: str, artist: str, lang: str) -> float:
    e_title, e_artist = entry.get("title"), entry.get("artist")
    if entry.get("kind") == "artist" or not e_title:
        # An artist alone answers «metti EMIN» (heard as a title, since there
        # is nothing else in the sentence) or the artist half of «X di EMIN».
        return phonetic_score(artist or title, e_artist, lang)
    title_score = phonetic_score(title, e_title, lang) if title else 0.0
    if not artist:
        return title_score
    if not e_artist:
        return 0.6 * title_score  # an artist was heard, and this has none
    return 0.6 * title_score + 0.4 * phonetic_score(artist, e_artist, lang)
