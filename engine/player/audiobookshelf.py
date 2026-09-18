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

from .errors import PlayerError
from .resilience import Resilient

#: The port Audiobookshelf listens on out of the box (its Docker image maps
#: 13378 to the container's 80).
DEFAULT_PORT = 13378

#: A transport takes ``{"path": str, "query": dict}`` and returns parsed JSON.
Transport = Callable[[Dict[str, Any]], Any]


class AudiobookshelfError(PlayerError):
    """Raised when Audiobookshelf cannot be reached or refuses a request."""


#: What the server's own refusals mean, in words worth putting in a log.
_STATUS_HINTS = {
    401: "Audiobookshelf refused the API key",
    403: "the API key's user may not see this",
    404: "Audiobookshelf has no such item (or the address is missing a path)",
}


def get(base_url: str, token: str, request: Dict[str, Any],
        timeout: float) -> Any:
    """One ``GET``, and its body as JSON.

    Every failure becomes an :class:`AudiobookshelfError`, the refusals the
    server states politely included: from here up "the bookshelf did not
    answer" is one outcome, and the detail is for the log.
    """
    query = {k: v for k, v in (request.get("query") or {}).items()
             if v is not None}
    url = base_url.rstrip("/") + request["path"]
    if query:
        url += "?" + urllib.parse.urlencode(query)
    http_request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}",
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        hint = _STATUS_HINTS.get(exc.code, "Audiobookshelf returned an error")
        raise AudiobookshelfError(
            f"{hint} ({exc.code}) for {request['path']}") from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise AudiobookshelfError(
            f"Audiobookshelf at {base_url} is not answering: {exc}") from exc
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise AudiobookshelfError(
            f"Audiobookshelf sent something that is not JSON: {exc}") from exc


class AudiobookshelfClient(Resilient):
    """One Audiobookshelf server, as the books its API key may read."""

    #: Every round trip fails as this, breaker and turn budget included.
    error = AudiobookshelfError

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
        return get(self.base_url, self.token, request, self._call_timeout())

    def _get(self, path: str, **query: Any) -> Any:
        return self._guarded({"path": path, "query": query})

    # -- the catalogue -----------------------------------------------------
    def book_libraries(self) -> List[Dict[str, Any]]:
        """``[{"id", "name"}, ...]`` for every book library the key can see."""
        answer = self._get("/api/libraries") or {}
        return [{"id": lib["id"], "name": lib.get("name") or ""}
                for lib in answer.get("libraries") or []
                if lib.get("mediaType") == "book" and lib.get("id")]

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
                               q=query, limit=count) or {}
            for match in answer.get("book") or []:
                book = _book(match.get("libraryItem") or {})
                if book is None or book["id"] in seen:
                    continue
                seen.add(book["id"])
                found.append(book)
                if len(found) >= count:
                    return found
        return found

    def stream_urls(self, item_id: str) -> List[str]:
        """The files of one book, in order, fetchable with no header at all.

        The key travels in the query string because the transport cannot be
        told to send one — see the module docstring. It is the same key the
        request itself used, so it grants nothing this client did not already
        have; but it is written into the hi-fi's queue, where anyone looking
        at that queue can read it, which is why ``--library-token`` asks for
        a key of its own, on a user that can only listen.
        """
        item = self._get(f"/api/items/{urllib.parse.quote(item_id, safe='')}",
                         expanded=1) or {}
        tracks = (item.get("media") or {}).get("tracks") or []
        suffix = "?" + urllib.parse.urlencode({"token": self.token})
        return [self.base_url + track["contentUrl"] + suffix
                for track in tracks if track.get("contentUrl")]


def _book(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """An expanded library item as the engine reads a book, or None for an
    item that has no audio to offer."""
    media = item.get("media") or {}
    if not item.get("id") or not media.get("tracks"):
        # An e-book with no audio, or an item whose files are all excluded:
        # found by the words, and nothing to listen to.
        return None
    metadata = media.get("metadata") or {}
    return {
        "id": item["id"],
        "title": metadata.get("title") or "",
        "author": metadata.get("authorName") or "",
        "duration": float(media.get("duration") or 0.0),
    }
