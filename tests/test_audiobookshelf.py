"""Audiobookshelf as a shelf of books: what it finds, and the URLs it hands out.

No network. :class:`FakeABSTransport` stands where the HTTP call would, in
the shape of ``FakeMATransport``; the handful of tests about the wire itself
replace ``urlopen`` instead, and look at the request it would have sent.
"""

import io
import json
import urllib.error
import urllib.parse

import pytest

from player import PlayerError
from player import audiobookshelf
from player.audiobookshelf import AudiobookshelfClient, AudiobookshelfError

BASE = "http://books.local:13378"
KEY = "k3y/with+odd=chars"


class FakeABSTransport:
    """Answers ``{"path", "query"}`` requests with whatever the test scripted.

    ``responses`` maps a path to a value or to ``callable(query)``; a path
    nobody scripted is a 404, which is what the server says too.
    """

    def __init__(self):
        self.calls = []
        self.responses = {}
        self.raise_on = set()

    def __call__(self, request):
        path, query = request["path"], dict(request.get("query") or {})
        self.calls.append((path, query))
        if path in self.raise_on or path not in self.responses:
            raise AudiobookshelfError(f"simulated failure for {path}")
        answer = self.responses[path]
        return answer(query) if callable(answer) else answer

    def paths(self):
        return [path for path, _ in self.calls]


def item(item_id, title="", author="", tracks=2, duration=3600.0):
    """An expanded library item as the server sends it."""
    return {
        "id": item_id,
        "mediaType": "book",
        "media": {
            "metadata": {"title": title, "authorName": author},
            "duration": duration,
            "tracks": [{"index": i + 1,
                        "contentUrl": f"/api/items/{item_id}/file/{100 + i}"}
                       for i in range(tracks)],
        },
    }


LIBRARIES = {"libraries": [
    {"id": "lib-a", "name": "Audiolibri", "mediaType": "book"},
    {"id": "lib-p", "name": "Podcast", "mediaType": "podcast"},
    {"id": "lib-k", "name": "Bambini", "mediaType": "book"},
]}


@pytest.fixture
def abs_transport():
    t = FakeABSTransport()
    t.responses["/api/libraries"] = LIBRARIES
    return t


@pytest.fixture
def shelf(abs_transport):
    return AudiobookshelfClient(BASE, token=KEY, transport=abs_transport)


# -- the libraries -------------------------------------------------------------

def test_only_book_libraries_are_shelves(shelf):
    # A podcast library is addressed by episode, not by item: searching it
    # for a book would find shows it cannot then play.
    assert shelf.book_libraries() == [{"id": "lib-a", "name": "Audiolibri"},
                                      {"id": "lib-k", "name": "Bambini"}]


def test_a_server_with_no_libraries_has_no_shelves(shelf, abs_transport):
    abs_transport.responses["/api/libraries"] = {"libraries": []}
    assert shelf.book_libraries() == []


# -- finding a book ------------------------------------------------------------

def test_a_book_is_found_on_the_second_shelf_too(shelf, abs_transport):
    abs_transport.responses["/api/libraries/lib-a/search"] = {"book": []}
    abs_transport.responses["/api/libraries/lib-k/search"] = {"book": [
        {"libraryItem": item("li-1", "Il piccolo principe",
                             "Antoine de Saint-Exupéry", duration=5400.5)}]}
    assert shelf.book_candidates("piccolo principe") == [{
        "id": "li-1", "title": "Il piccolo principe",
        "author": "Antoine de Saint-Exupéry", "duration": 5400.5}]
    assert abs_transport.paths() == [
        "/api/libraries", "/api/libraries/lib-a/search",
        "/api/libraries/lib-k/search"]


def test_the_servers_order_is_kept_and_the_count_honoured(shelf, abs_transport):
    abs_transport.responses["/api/libraries/lib-a/search"] = lambda q: {
        "book": [{"libraryItem": item(f"a{i}", f"Libro {i}")} for i in range(3)]}
    abs_transport.responses["/api/libraries/lib-k/search"] = {"book": [
        {"libraryItem": item("k0", "Altro")}]}
    found = shelf.book_candidates("libro", count=2)
    assert [b["id"] for b in found] == ["a0", "a1"]
    # The count is also what the server is asked for, and a full answer from
    # the first shelf spares the second one the round trip.
    assert abs_transport.calls[1] == ("/api/libraries/lib-a/search",
                                      {"q": "libro", "limit": 2})
    assert "/api/libraries/lib-k/search" not in abs_transport.paths()


def test_an_item_with_nothing_to_listen_to_is_not_a_candidate(shelf, abs_transport):
    # An e-book matches the words and has no audio: offering it would be
    # offering a silence.
    abs_transport.responses["/api/libraries/lib-a/search"] = {"book": [
        {"libraryItem": item("ebook", "Solo testo", tracks=0)},
        {"libraryItem": item("audio", "Con audio")}]}
    abs_transport.responses["/api/libraries/lib-k/search"] = {}
    assert [b["id"] for b in shelf.book_candidates("testo")] == ["audio"]


def test_missing_metadata_does_not_break_a_candidate(shelf, abs_transport):
    bare = {"id": "li-9", "media": {"tracks": [{"contentUrl": "/x"}]}}
    abs_transport.responses["/api/libraries/lib-a/search"] = {"book": [
        {"libraryItem": bare}]}
    abs_transport.responses["/api/libraries/lib-k/search"] = {"book": None}
    assert shelf.book_candidates("x") == [
        {"id": "li-9", "title": "", "author": "", "duration": 0.0}]


@pytest.mark.parametrize("query", ["", "   ", None])
def test_an_empty_query_asks_nothing(shelf, abs_transport, query):
    assert shelf.book_candidates(query) == []
    assert abs_transport.calls == []


# -- the files -----------------------------------------------------------------

def test_stream_urls_are_absolute_ordered_and_carry_the_key(shelf, abs_transport):
    abs_transport.responses["/api/items/li-1"] = item("li-1", tracks=3)
    urls = shelf.stream_urls("li-1")
    assert [urllib.parse.urlsplit(u).path for u in urls] == [
        "/api/items/li-1/file/100", "/api/items/li-1/file/101",
        "/api/items/li-1/file/102"]
    for url in urls:
        parts = urllib.parse.urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}" == BASE
        # The hi-fi cannot send a header, so the key rides in the query —
        # and it has to survive the trip intact, odd characters and all.
        assert urllib.parse.parse_qs(parts.query) == {"token": [KEY]}
    assert abs_transport.calls[0] == ("/api/items/li-1", {"expanded": 1})


def test_a_path_prefix_is_kept_in_every_url(abs_transport):
    # Behind a reverse proxy the server lives under a path. contentUrl is
    # server-relative, so dropping the prefix would hand the hi-fi a 404.
    shelf = AudiobookshelfClient("https://home.example/audiobookshelf/",
                                 token="k", transport=abs_transport)
    abs_transport.responses["/api/items/li-1"] = item("li-1", tracks=1)
    assert shelf.stream_urls("li-1") == [
        "https://home.example/audiobookshelf/api/items/li-1/file/100?token=k"]


def test_an_item_id_cannot_walk_out_of_its_path(shelf, abs_transport):
    abs_transport.responses["/api/items/..%2Flibraries"] = item("x", tracks=0)
    assert shelf.stream_urls("../libraries") == []
    assert abs_transport.paths() == ["/api/items/..%2Flibraries"]


def test_an_item_with_no_audio_streams_nothing(shelf, abs_transport):
    abs_transport.responses["/api/items/ebook"] = item("ebook", tracks=0)
    assert shelf.stream_urls("ebook") == []


# -- failure -------------------------------------------------------------------

def test_a_failure_is_a_player_error(shelf, abs_transport):
    # The engine catches PlayerError and apologises; anything else would
    # crash the turn instead.
    abs_transport.raise_on.add("/api/libraries")
    with pytest.raises(PlayerError):
        shelf.book_libraries()


def test_construction_dials_nothing(abs_transport):
    AudiobookshelfClient(BASE, token=KEY, transport=abs_transport)
    assert abs_transport.calls == []


def test_an_address_is_required():
    with pytest.raises(ValueError):
        AudiobookshelfClient("", token=KEY)


# -- the wire ------------------------------------------------------------------

class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_wire_sends_a_bearer_get_with_the_query(monkeypatch):
    sent = []

    def urlopen(request, timeout):
        sent.append((request, timeout))
        return _Response(json.dumps({"libraries": []}).encode())

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    shelf = AudiobookshelfClient(BASE + "/", token=KEY, timeout=4.0)
    shelf._get("/api/libraries/lib-a/search", q="l'isola del tesoro", limit=5)
    request, timeout = sent[0]
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    parts = urllib.parse.urlsplit(request.full_url)
    assert parts.path == "/api/libraries/lib-a/search"
    assert urllib.parse.parse_qs(parts.query) == {
        "q": ["l'isola del tesoro"], "limit": ["5"]}
    assert timeout == 4.0


@pytest.mark.parametrize("code, words", [(401, "refused the API key"),
                                         (404, "no such item")])
def test_a_refusal_is_named_in_the_error(monkeypatch, code, words):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "no", {}, None)

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfError, match=words):
        audiobookshelf.get(BASE, KEY, {"path": "/api/items/x"}, 1.0)


def test_an_unreachable_server_is_an_error_not_a_crash(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfError, match="not answering"):
        audiobookshelf.get(BASE, KEY, {"path": "/api/libraries"}, 1.0)


def test_a_body_that_is_not_json_is_an_error(monkeypatch):
    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen",
                        lambda request, timeout: _Response(b"<html>login</html>"))
    with pytest.raises(AudiobookshelfError, match="not JSON"):
        audiobookshelf.get(BASE, KEY, {"path": "/api/libraries"}, 1.0)
