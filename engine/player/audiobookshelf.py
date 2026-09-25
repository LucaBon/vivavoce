"""Audiobookshelf, as a shelf of books heard through somebody else's speakers.

Audiobookshelf is a self-hosted server for audiobooks and podcasts. It keeps
the catalogue, the files and each listener's progress, and it plays nothing
in the room: its own apps stream to the phone in your hand. That is exactly
the shape :class:`~player.protocols.SpokenLibrary` describes, so this client
answers two questions and only two — which books match these words, and
which files make up this book — and leaves the playing to whichever music
system Vivavoce is already driving (:mod:`player.composite`).

The wire is plain REST over ``urllib``, for the reason ``ma_transport``
gives: no dependency is how this project installs anywhere.

Verified against ``advplyr/audiobookshelf`` v2.36.1 on 2026-09-17:

- ``GET /api/libraries`` answers ``{"libraries": [{"id", "name",
  "mediaType"}, ...]}``, already narrowed to what the token's user may see
  (``LibraryController.findAll``).
- ``GET /api/libraries/<id>/search?q=&limit=`` answers ``{"book": [{"libraryItem":
  {...expanded}}], "authors": [...], "series": [...], ...}`` for a book
  library (``libraryItemsBookFilters.search``). The expanded item carries
  ``media.metadata.title`` / ``authorName``, ``media.duration`` and
  ``media.tracks``.
- ``GET /api/items/<id>?expanded=1`` answers the same item on its own, and
  ``media.tracks[].contentUrl`` is ``/api/items/<id>/file/<ino>``
  (``Book.getTracklist``), already excluding the files marked excluded and in
  listening order.
- Authentication is a bearer token — an API key made under *Settings → API
  Keys* — and ``Auth.js`` reads it from **either** the ``Authorization``
  header **or** a ``token`` query parameter
  (``ExtractJwt.fromUrlQueryParameter('token')``). The second is what makes a
  file URL something an LMS can fetch: a hi-fi asked to play a URL cannot be
  told to send a header with it.

Podcast libraries are skipped on purpose. An episode is not addressed by the
item id alone (``/api/items/<id>/play/<episodeId>``), and a podcast is a
different conversation — «l'ultima puntata di» — that belongs with the
sentences that will reach it, not smuggled in here.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .errors import (PlayerError, PlayerRefused, PlayerUnreachable,
                     never_delivered)
from .resilience import Resilient

#: The port Audiobookshelf listens on out of the box (its Docker image maps
#: 13378 to the container's 80).
DEFAULT_PORT = 13378

#: A transport takes ``{"path": str, "query": dict}`` and returns parsed JSON.
Transport = Callable[[Dict[str, Any]], Any]


class AudiobookshelfError(PlayerError):
    """Raised when Audiobookshelf cannot be reached or refuses a request."""


class AudiobookshelfUnreachable(AudiobookshelfError, PlayerUnreachable):
    """Audiobookshelf gave no answer (see ``player/errors.py``)."""


class AudiobookshelfRefused(AudiobookshelfError, PlayerRefused):
    """Audiobookshelf answered, and it was a refusal or not what was asked."""


#: Statuses that come from whatever stands in front of Audiobookshelf rather
#: than from it. Not a hypothetical here: this client is written for a server
#: reached through a reverse proxy (see the module docstring), and a proxy
#: that cannot reach it is silence wearing a status code.
_GATEWAY_STATUSES = (502, 504)


#: What the server's own refusals mean, in words worth putting in a log.
_STATUS_HINTS = {
    401: "Audiobookshelf refused the API key",
    403: "the API key's user may not see this",
    404: "Audiobookshelf has no such item (or the address is missing a path)",
}


def call(base_url: str, token: str, request: Dict[str, Any],
         timeout: float) -> Any:
    """One request, and its reply body as JSON.

    A ``GET`` unless the request names a ``method``, and any other method is
    a write: its ``body`` goes as JSON, and the reply is not read —
    Audiobookshelf answers a progress ``PATCH`` with a bare «OK», which is
    not JSON, and a write has nothing to report back but its status.

    Every failure is an :class:`AudiobookshelfError`, because from the engine
    up "the bookshelf did not answer" is one outcome and the detail is for
    the log. The client itself does care which it was, in the two ways
    ``player/resilience.py`` describes: a refused key is proof the server is
    there, and a reply that never came may still have been acted on. So the
    two kinds are told apart here, where the difference is visible.
    """
    query = {k: v for k, v in (request.get("query") or {}).items()
             if v is not None}
    url = base_url.rstrip("/") + request["path"]
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    method = request.get("method") or "GET"
    write = method != "GET"
    data = None
    if write and request.get("body") is not None:
        data = json.dumps(request["body"]).encode()
        headers["Content-Type"] = "application/json"
    http_request = urllib.request.Request(url, data=data, headers=headers,
                                          method=method)
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            payload = None if write else response.read()
    except urllib.error.HTTPError as exc:
        hint = _STATUS_HINTS.get(exc.code, "Audiobookshelf returned an error")
        kind = (AudiobookshelfUnreachable if exc.code in _GATEWAY_STATUSES
                else AudiobookshelfRefused)
        error = kind(f"{hint} ({exc.code}) for {request['path']}")
        # Carried for callers that need to tell one refusal from another —
        # ``progress()`` reads a 404 as "never started", not as a failure.
        error.status = exc.code
        raise error from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise AudiobookshelfUnreachable(
            f"Audiobookshelf at {base_url} is not answering: {exc}",
            delivered=not never_delivered(exc)) from exc
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise AudiobookshelfRefused(
            f"Audiobookshelf sent something that is not JSON: {exc}") from exc


class AudiobookshelfClient(Resilient):
    """One Audiobookshelf server, as the books its API key may read."""

    #: Every round trip fails as this, breaker and turn budget included,
    #: and as one of its two kinds where the wire says which (see above).
    error = AudiobookshelfError
    unreachable = AudiobookshelfUnreachable
    refused = AudiobookshelfRefused

    #: How this catalogue is spelled in a reply that names it — see
    #: ``player.protocols.system_label``.
    SYSTEM_LABEL = "Audiobookshelf"

    def __init__(self, base_url: str, token: str = "", timeout: float = 8.0,
                 transport: Optional[Transport] = None) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        # Kept with any path prefix it came with: behind a reverse proxy the
        # server lives at /audiobookshelf, and every URL below — the API
        # calls and the file URLs handed to the hi-fi — has to keep it.
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._transport: Transport = transport or self._http_transport
        self._init_resilience(timeout)

    def _http_transport(self, request: Dict[str, Any]) -> Any:
        return call(self.base_url, self.token, request, self._call_timeout())

    def _repeat_safe(self, request: Dict[str, Any]) -> bool:
        """Every request this client makes is safe to send twice.

        Almost all are a ``GET`` of the catalogue: a shelf is read, and the
        books on it are played by whatever backend the engine was handed
        (``player/composite.py``). The one write, :meth:`save_progress`,
        carries an absolute position — «at 350 s», never «35 s further» — so
        a second copy leaves the server exactly where the first did. A reply
        that went missing is therefore always worth asking for again — which
        is the difference between one dropped packet and «l'impianto non
        risponde».
        """
        return True

    def _get(self, path: str, **query: Any) -> Dict[str, Any]:
        """One ``GET``, and its body as the JSON **object** the API documents.

        Anything else that is still valid JSON — a list, a string, a number —
        is an answer from something that is not an Audiobookshelf: a captive
        portal, a reverse-proxy error page that happens to parse, or a schema
        that moved under us. ``call()`` above already converts a body that is
        not JSON at all; this is the other half of the same boundary, and
        without it the shape reached ``.get()`` three frames up as
        ``AttributeError: 'list' object has no attribute 'get'``.

        Which is not a :class:`~player.errors.PlayerError`, so nobody caught
        it: ``spoken_library.open_library`` guards the probe with
        ``except PlayerError``, and the exception came out of ``server.main``
        instead — the whole voice assistant refusing to start because a
        bookshelf answered oddly. The music has nothing to do with the books.
        """
        answer = self._guarded({"path": path, "query": query})
        if answer is None or isinstance(answer, dict):
            return answer or {}
        raise AudiobookshelfRefused(
            f"Audiobookshelf answered {path} with a "
            f"{type(answer).__name__}, not an object")

    # -- the catalogue -----------------------------------------------------
    def book_libraries(self) -> List[Dict[str, Any]]:
        """``[{"id", "name"}, ...]`` for every book library the key can see."""
        return [{"id": lib["id"], "name": lib.get("name") or ""}
                for lib in self._get("/api/libraries").get("libraries") or []
                # ``isinstance`` per row, not just on the envelope: one shelf
                # that is not an object must not take the shelves beside it
                # that are perfectly fine.
                if isinstance(lib, dict)
                and lib.get("mediaType") == "book" and lib.get("id")]

    def book_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        """Books matching ``query`` across every book library, in the order
        the server ranked them, library by library.

        One search per library, because that is the only search the API has.
        A household has one or two — «Audiolibri», «Bambini» — so this is one
        extra round trip at most, and it keeps a book on the second shelf
        from being unfindable.
        """
        query = (query or "").strip()
        if not query or count <= 0:
            return []
        found: List[Dict[str, Any]] = []
        seen = set()
        for library in self.book_libraries():
            answer = self._get(f"/api/libraries/{library['id']}/search",
                               q=query, limit=count)
            for match in answer.get("book") or []:
                if not isinstance(match, dict):
                    continue
                book = _book(match.get("libraryItem"))
                if book is None or book["id"] in seen:
                    continue
                seen.add(book["id"])
                found.append(book)
                if len(found) >= count:
                    return found
        return found

    def stream_urls(self, item_id: str) -> List[str]:
        """The files of one book, in order, fetchable with no header at all.

        Built on :meth:`tracks`, which is the one that actually asks — this
        is only the URLs of what it returns, for a caller that has no use
        for the durations beside them.
        """
        return [t["url"] for t in self.tracks(item_id)]

    def tracks(self, item_id: str) -> List[Dict[str, Any]]:
        """The files of one book, in order, as ``{"url", "duration"}``.

        ``duration`` is seconds, ``0.0`` when the server did not say — which
        is how :func:`player.composite.Composite.enqueue` tells "resume this
        book partway through" from "the files are what they are, play them
        from the start": it needs the length of each file to find *which*
        file a resume point falls in, and this is the one call that already
        fetches the item ``stream_urls`` fetches, so a resume costs nothing
        extra on the wire.

        The key travels in the query string because the transport cannot be
        told to send one — see the module docstring. It is the same key the
        request itself used, so it grants nothing this client did not already
        have; but it is written into the hi-fi's queue, where anyone looking
        at that queue can read it, which is why ``--library-token`` asks for
        a key of its own, on a user that can only listen.
        """
        item = self._get(f"/api/items/{urllib.parse.quote(item_id, safe='')}",
                         expanded=1)
        media = item.get("media")
        tracks = media.get("tracks") if isinstance(media, dict) else None
        suffix = "?" + urllib.parse.urlencode({"token": self.token})
        return [{"url": self.base_url + track["contentUrl"] + suffix,
                "duration": _seconds(track.get("duration"))}
                for track in tracks or []
                if isinstance(track, dict)
                and isinstance(track.get("contentUrl"), str)]

    def chapters(self, item_id: str) -> List[Dict[str, Any]]:
        """The chapters of one book as ``{"start", "end", "title"}``, in
        listening order — seconds from the beginning of the whole book, not
        of any one file, which is why a single ``.m4b`` and a folder of MP3s
        read the same here.

        Empty for a book the server has no chapters for: the caller decides
        what a chapter is then (:meth:`player.composite.Composite.chapter_at`
        falls back to the files). Sorted by ``start`` because the server's
        own order is by ``id``, and a chapter list edited in its UI can hold
        the two apart.
        """
        item = self._get(f"/api/items/{urllib.parse.quote(item_id, safe='')}",
                         expanded=1)
        media = item.get("media")
        chapters = media.get("chapters") if isinstance(media, dict) else None
        found = [{"start": _seconds(ch.get("start")),
                  "end": _seconds(ch.get("end")),
                  "title": ch.get("title") if isinstance(ch.get("title"), str) else ""}
                 for ch in chapters or []
                 if isinstance(ch, dict) and ch.get("start") is not None]
        return sorted(found, key=lambda ch: ch["start"])

    def save_progress(self, item_id: str, position: float,
                      duration: Optional[float]) -> None:
        """Tell Audiobookshelf the listener is ``position`` seconds into
        ``item_id`` — the record :meth:`progress` reads, and the one its own
        app resumes from (T5.5: it owns this fact, nothing here stores it).

        ``PATCH /api/me/progress/<id>``, verified against ``advplyr/
        audiobookshelf`` on 2026-09-25 (``MeController.createUpdateMediaProgress``
        → ``User.createUpdateMediaProgressFromPayload``). The server computes
        nothing: ``progress`` is stored as sent, and a ``duration`` not sent
        is stored as 0. So both go only when the book's length is known, and
        a position alone otherwise. ``isFinished`` is never sent: finishing
        a book is the app's business, not a sampler's.
        """
        body: Dict[str, Any] = {"currentTime": position}
        if duration:
            body["duration"] = duration
            body["progress"] = min(1.0, position / duration)
        self._guarded({
            "path": f"/api/me/progress/{urllib.parse.quote(item_id, safe='')}",
            "method": "PATCH", "body": body})

    def progress(self, item_id: str) -> Optional[float]:
        """How far into ``item_id`` the last listener got, in seconds — or
        ``None`` for a book never started, or finished (``isFinished``:
        starting over is what "riprendi" should do with nothing left to
        resume).

        Audiobookshelf owns this fact; nothing here stores it (T5.5). A book
        the server has no record of answers ``404`` — "never started" and
        "no such item" are the same reply from its side, and the caller
        already lost the second case at ``book_candidates`` if it mattered.
        """
        try:
            answer = self._get(
                f"/api/me/progress/{urllib.parse.quote(item_id, safe='')}")
        except AudiobookshelfRefused as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise
        if not answer or answer.get("isFinished"):
            return None
        return _seconds(answer.get("currentTime"))


def _book(item: Any) -> Optional[Dict[str, Any]]:
    """An expanded library item as the engine reads a book, or None for an
    item that has no audio to offer — or no shape this can read at all."""
    if not isinstance(item, dict):
        return None
    media = item.get("media")
    media = media if isinstance(media, dict) else {}
    if not item.get("id") or not media.get("tracks"):
        # An e-book with no audio, or an item whose files are all excluded:
        # found by the words, and nothing to listen to.
        return None
    metadata = media.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "id": item["id"],
        "title": metadata.get("title") or "",
        "author": metadata.get("authorName") or "",
        # A duration the server wrote as words is not a reason to lose the
        # book: it is read out nowhere, and only orders the list.
        "duration": _seconds(media.get("duration")),
    }


def _seconds(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
