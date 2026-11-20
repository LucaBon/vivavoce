"""A hi-fi that exists only in memory, for the public demo.

The Router the demo page talks to is the real one — ``engine/`` and
``localvoice/`` as they ship, loaded into the browser by Pyodide. This is the
one thing it cannot have there: a music system. So this module is one, small
and honest, built the way ``tests/test_capabilities.py`` builds its speakers:
duck-typed, holding exactly the methods its :class:`Capabilities` promise and
nothing else, so a branch of the engine that forgot to ask fails here the way
it would on a real partial backend.

The catalogue is chosen for the cases the demo exists to show. Two records are
called «Time»; «Wish You Were Here» is not here at all, and «Here Comes the
Sun» is — so a keyword search (``naive.py``, the page's comparison) has
something wrong to play for it. «metti Time di Hans
Zimmer» must start Zimmer's, and a song it has not got must be *said*, not
replaced by the first hit.

That last one rests on the search: :meth:`DemoHifi.search_tracks` answers
nothing when nothing matches, like TIDAL and Qobuz do — which is what lets
``actions._resolve_song`` read "the catalogue put it first" as evidence at all.
It is strict on purpose: every word asked must be on the record. A looser one
answered «Money for Nothing» with «Money», which a real catalogue never would
— it has the Dire Straits record — and this shelf of six cannot.
Stdlib only, and no ``service`` attribute: this system has no streaming
services to name, and naming one would put «da TIDAL» in its replies.
"""

from __future__ import annotations

import contextlib
import time
import unicodedata
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from player.protocols import Capabilities

#: title, artist, album, seconds. Order is the catalogue's own ranking.
CATALOGUE = (
    ("Time", "Pink Floyd", "The Dark Side of the Moon", 413),
    ("Money", "Pink Floyd", "The Dark Side of the Moon", 382),
    ("Breathe", "Pink Floyd", "The Dark Side of the Moon", 163),
    ("Time", "Hans Zimmer", "Inception", 275),
    ("Bohemian Rhapsody", "Queen", "A Night at the Opera", 354),
    ("Clair de lune", "Claude Debussy", "Suite bergamasque", 300),
    ("Here Comes the Sun", "The Beatles", "Abbey Road", 185),
)


def _words(text: str) -> List[str]:
    """Lower-case, accent-free words: «Clair de Lune» and «clair de lune»
    are the same search, as they are to any real catalogue."""
    plain = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in plain if not unicodedata.combining(c)).lower()
    return "".join(c if c.isalnum() else " " for c in plain).split()


def _track(n: int) -> Dict[str, Any]:
    title, artist, album, duration = CATALOGUE[n]
    return {"url": f"demo://track/{n + 1}", "id": f"demo://track/{n + 1}",
            "title": title, "artist": artist, "album": album,
            "duration": duration}


def _matches(query: str, *fields: str) -> bool:
    """Every word of the query is somewhere in the fields, as many times as it
    was said («Money Money Money» is ABBA, not Pink Floyd) — and a query with
    no words matches nothing, rather than everything."""
    wanted = Counter(_words(query))
    have = Counter(_words(" ".join(fields)))
    return bool(wanted) and all(have[w] >= n for w, n in wanted.items())


class DemoHifi:
    """A catalogue of six tracks and one player that plays them in silence."""

    capabilities = Capabilities(search=True, browse_items=True, seek=True)

    def __init__(self, now: Callable[[], float] = time.monotonic):
        self.player_id = "demo"
        self.base_url = "demo://hifi"
        self.calls: List[tuple] = []
        self._now = now
        self._queue: List[Dict[str, Any]] = []
        self._index = 0
        self._mode = "stop"
        self._elapsed = 0.0
        self._since: Optional[float] = None
        self._volume = 50

    # -- what was said to it -------------------------------------------------
    def _say(self, name: str, *args: Any) -> Dict[str, Any]:
        self.calls.append((name, args))
        return {}

    def url_of(self, title: str, artist: str) -> str:
        for n, row in enumerate(CATALOGUE):
            if row[:2] == (title, artist):
                return _track(n)["url"]
        raise KeyError((title, artist))

    @contextlib.contextmanager
    def turn_deadline(self, seconds: float):
        yield

    # -- the clock -------------------------------------------------------------
    def _position(self) -> float:
        self._play_on()
        if self._mode == "play" and self._since is not None:
            return self._elapsed + (self._now() - self._since)
        return self._elapsed

    def _play_on(self) -> None:
        """What a real player does between two questions: finish a record
        and start the next, or stop at the end of the queue."""
        while self._mode == "play" and self._since is not None:
            track = self._queue[self._index]
            over = self._elapsed + (self._now() - self._since) - track["duration"]
            if over < 0:
                return
            if self._index + 1 >= len(self._queue):
                self._stop(at=float(track["duration"]))
                return
            self._index += 1
            self._elapsed, self._since = 0.0, self._now() - over

    def _start(self, at: float = 0.0) -> None:
        if self._current() is None:
            self._stop()
            return
        self._elapsed, self._since, self._mode = at, self._now(), "play"

    def _stop(self, at: float = 0.0) -> None:
        self._elapsed, self._since, self._mode = at, None, "stop"

    def _current(self) -> Optional[Dict[str, Any]]:
        if 0 <= self._index < len(self._queue):
            return self._queue[self._index]
        return None

    # -- the transport ---------------------------------------------------------
    def pause(self):
        at = self._position()
        if self._mode == "play":
            self._elapsed, self._mode = at, "pause"
        return self._say("pause")

    def resume(self):
        self._play_on()
        if self._mode == "pause" and self._current():
            self._start(self._elapsed)
        elif self._mode == "stop" and self._current():
            self._start()
        return self._say("resume")

    def next_track(self):
        self._play_on()
        if self._index + 1 < len(self._queue):
            self._index += 1
            self._start()
        else:
            self._stop()
        return self._say("next_track")

    def previous_track(self):
        self._play_on()
        if self._index > 0:
            self._index -= 1
        if self._current():
            self._start()
        return self._say("previous_track")

    def volume(self, delta):
        self._volume = max(0, min(100, self._volume + int(delta)))
        return self._say("volume", delta)

    def volume_set(self, value):
        self._volume = max(0, min(100, int(value)))
        return self._say("volume_set", value)

    def seek(self, seconds):
        self._play_on()
        if self._current():
            self._elapsed = float(seconds)
            self._since = self._now()
        return self._say("seek", seconds)

    def clear_queue(self):
        self._queue, self._index = [], 0
        self._stop()
        return self._say("clear_queue")

    def queue_upcoming(self, limit: int = 5) -> List[Dict[str, Any]]:
        self._play_on()
        return [{"title": t["title"], "artist": t["artist"]}
                for t in self._queue[self._index + 1:self._index + 1 + limit]]

    def now_playing_info(self) -> Optional[Dict[str, Any]]:
        self._play_on()
        track = self._current()
        if not track:
            return None
        return {"title": track["title"], "artist": track["artist"],
                "mode": self._mode, "index": self._index,
                "elapsed": self._position(), "connected": True}

    def status_info(self) -> Dict[str, Any]:
        self._play_on()
        track = self._current()
        if not track:
            return {"mode": "stop", "volume": self._volume}
        return {"mode": self._mode, "title": track["title"],
                "artist": track["artist"], "album": track["album"],
                "duration": track["duration"],
                "elapsed": min(self._position(), track["duration"]),
                "volume": self._volume}

    # -- starting something ----------------------------------------------------
    def _by_url(self, url: str) -> Dict[str, Any]:
        for n in range(len(CATALOGUE)):
            if _track(n)["url"] == url:
                return _track(n)
        return {"url": url, "title": url, "artist": "", "album": "",
                "duration": 0}

    def play_url(self, url):
        self._queue, self._index = [self._by_url(url)], 0
        self._start()
        return self._say("play_url", url)

    def add_url(self, url):
        self._queue.append(self._by_url(url))
        return self._say("add_url", url)

    def insert_url(self, url):
        self._play_on()
        self._queue.insert(self._index + 1, self._by_url(url))
        return self._say("insert_url", url)

    def play_tracks(self, tracks):
        self._queue = [self._by_url(t["url"] if isinstance(t, dict) else t)
                       for t in tracks]
        self._index = 0
        self._start()
        return self._say("play_tracks", [t["url"] for t in self._queue])

    def _tracks_for(self, item_id: str) -> List[Dict[str, Any]]:
        """What an id from this catalogue plays: one track, or every track
        of the album or the artist it names (see :meth:`_names`)."""
        for n in range(len(CATALOGUE)):
            if _track(n)["id"] == item_id:
                return [_track(n)]
        for column in (1, 2):
            prefix = f"demo://{column}/"
            if item_id.startswith(prefix):
                name = item_id[len(prefix):]
                return [_track(n) for n, row in enumerate(CATALOGUE)
                        if row[column] == name]
        return []

    def play_browse_item(self, item_id):
        self._queue, self._index = self._tracks_for(item_id), 0
        self._start()
        return self._say("play_browse_item", item_id)

    def add_browse_item(self, item_id):
        self._queue.extend(self._tracks_for(item_id))
        return self._say("add_browse_item", item_id)

    def insert_browse_item(self, item_id):
        self._play_on()
        at = self._index + 1
        self._queue[at:at] = self._tracks_for(item_id)
        return self._say("insert_browse_item", item_id)

    # The library is the catalogue: there is nothing here that is not "local".
    play_local_album = play_local_artist = play_local_track = play_browse_item
    add_local_album = add_local_artist = add_local_track = add_browse_item
    insert_local_album = insert_local_artist = insert_local_track = insert_browse_item

    # -- the catalogue ---------------------------------------------------------
    def search_tracks(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        found = [_track(n) for n, (title, artist, album, _) in enumerate(CATALOGUE)
                 if _matches(query, title, artist, album)]
        return found[:count]

    def track_url(self, item_id: str) -> Optional[str]:
        return item_id

    def _names(self, column: int, query: str) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        for title, artist, album, _ in CATALOGUE:
            name = (title, artist, album)[column]
            if name not in seen and _matches(query, name):
                seen[name] = {"id": f"demo://{column}/{name}", "title": name}
                if column == 2:
                    seen[name]["artist"] = artist
        return list(seen.values())

    def album_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return self._names(2, query)[:count]

    def find_album(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        found = self.album_candidates(query, count)
        return found[0] if found else None

    def album_tracks(self, query: str, count: int = 50) -> Dict[str, Any]:
        album = self.find_album(query)
        if not album:
            return {"album": None, "tracks": []}
        tracks = [_track(n) for n, row in enumerate(CATALOGUE)
                  if row[2] == album["title"]]
        return {"album": album, "tracks": tracks[:count]}

    def artist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return self._names(1, query)[:count]

    def find_artist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        found = self.artist_candidates(query, count)
        return found[0] if found else None

    def artist_tracks(self, artist: Dict[str, Any],
                      count: int = 20) -> List[Dict[str, Any]]:
        return [_track(n) for n, row in enumerate(CATALOGUE)
                if row[1] == artist.get("title")][:count]

    def artist_top_tracks(self, query: str, count: int = 20) -> Dict[str, Any]:
        artist = self.find_artist(query)
        if not artist:
            return {"artist": None, "tracks": []}
        return {"artist": artist, "tracks": self.artist_tracks(artist, count)}

    def playlist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return []

    def find_playlist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        return None
