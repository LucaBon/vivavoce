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
from player.audiobookshelf import (AudiobookshelfClient, AudiobookshelfError,
                                   AudiobookshelfRefused,
                                   AudiobookshelfUnreachable)

BASE = "http://books.local:13378"
KEY = "k3y/with+odd=chars"


class FakeABSTransport:
    """Answers ``{"path", "query"}`` requests with whatever the test scripted.

    ``responses`` maps a path to a value or to ``callable(query)``; a path
    nobody scripted is a 404, which is what the server says too.
    """

    def __init__(self):
        self.calls = []
        self.requests = []
        self.responses = {}
        self.raise_on = set()

    def __call__(self, request):
        path, query = request["path"], dict(request.get("query") or {})
        self.calls.append((path, query))
        self.requests.append(request)
        if path in self.raise_on or path not in self.responses:
            raise AudiobookshelfError(f"simulated failure for {path}")
        answer = self.responses[path]
        if isinstance(answer, BaseException):
            raise answer
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


def test_tracks_carries_the_duration_stream_urls_drops(shelf, abs_transport):
    # stream_urls is built on tracks() (T5.6): one HTTP call serves both, and
    # a resume needs the durations stream_urls never had a reason to keep.
    abs_transport.responses["/api/items/li-1"] = {
        "media": {"tracks": [
            {"contentUrl": "/api/items/li-1/file/100", "duration": 600.0},
            {"contentUrl": "/api/items/li-1/file/101", "duration": 700.5}]}}
    found = shelf.tracks("li-1")
    assert [t["duration"] for t in found] == [600.0, 700.5]
    assert [urllib.parse.urlsplit(t["url"]).path for t in found] == [
        "/api/items/li-1/file/100", "/api/items/li-1/file/101"]
    assert abs_transport.calls == [("/api/items/li-1", {"expanded": 1})]


def test_a_track_with_no_duration_is_zero(shelf, abs_transport):
    abs_transport.responses["/api/items/li-1"] = {
        "media": {"tracks": [{"contentUrl": "/s/1.m4b"}]}}
    assert shelf.tracks("li-1")[0]["duration"] == 0.0


# -- chapters --------------------------------------------------------------

def test_chapters_are_read_off_the_item_in_order(shelf, abs_transport):
    # The server's own order is by ``id``; the book's is by ``start``, and a
    # chapter list edited by hand in its UI can hold the two apart.
    abs_transport.responses["/api/items/li-1"] = {"media": {"chapters": [
        {"id": 1, "start": 1200.5, "end": 2400, "title": "Un incontro"},
        {"id": 0, "start": 0, "end": 1200.5, "title": "Capitolo 1"}]}}
    assert shelf.chapters("li-1") == [
        {"start": 0.0, "end": 1200.5, "title": "Capitolo 1"},
        {"start": 1200.5, "end": 2400.0, "title": "Un incontro"}]
    assert abs_transport.calls == [("/api/items/li-1", {"expanded": 1})]


@pytest.mark.parametrize("media", [
    {}, {"chapters": None}, {"chapters": []},
    {"chapters": ["not a chapter", {"title": "no start"}]},
])
def test_a_book_without_chapters_has_none(shelf, abs_transport, media):
    abs_transport.responses["/api/items/li-1"] = {"media": media}
    assert shelf.chapters("li-1") == []


def test_a_chapter_with_no_title_or_end_is_still_a_chapter(shelf, abs_transport):
    abs_transport.responses["/api/items/li-1"] = {"media": {"chapters": [
        {"start": 0}]}}
    assert shelf.chapters("li-1") == [{"start": 0.0, "end": 0.0, "title": ""}]


# -- progress --------------------------------------------------------------

def _refusal(status):
    exc = AudiobookshelfRefused(f"answered ({status})")
    exc.status = status
    return exc


def test_progress_reads_the_current_position(shelf, abs_transport):
    abs_transport.responses["/api/me/progress/li-1"] = {
        "currentTime": 754.0, "isFinished": False}
    assert shelf.progress("li-1") == 754.0
    assert abs_transport.calls[0] == ("/api/me/progress/li-1", {})


def test_a_book_never_started_has_no_progress(shelf, abs_transport):
    # 404 is what Audiobookshelf says for "no such progress row" as much as
    # for "no such item" — see _STATUS_HINTS — and here it means "never
    # started", not a failure.
    abs_transport.responses["/api/me/progress/li-1"] = _refusal(404)
    assert shelf.progress("li-1") is None


def test_a_finished_book_starts_over(shelf, abs_transport):
    abs_transport.responses["/api/me/progress/li-1"] = {
        "currentTime": 36000.0, "isFinished": True}
    assert shelf.progress("li-1") is None


def test_a_refusal_that_is_not_a_404_still_raises(shelf, abs_transport):
    abs_transport.responses["/api/me/progress/li-1"] = _refusal(401)
    with pytest.raises(AudiobookshelfRefused):
        shelf.progress("li-1")


def test_save_progress_patches_the_position_the_duration_and_the_fraction(
        shelf, abs_transport):
    abs_transport.responses["/api/me/progress/li-1"] = None
    shelf.save_progress("li-1", 350.0, 1400.0)
    assert abs_transport.requests == [{
        "path": "/api/me/progress/li-1", "method": "PATCH",
        "body": {"currentTime": 350.0, "duration": 1400.0, "progress": 0.25}}]


def test_a_book_of_unknown_length_saves_the_position_alone(shelf, abs_transport):
    # The server does not compute progress, and a duration it is not sent
    # it stores as 0: sending neither beats sending a wrong one.
    abs_transport.responses["/api/me/progress/li-1"] = None
    shelf.save_progress("li-1", 350.0, None)
    assert abs_transport.requests[0]["body"] == {"currentTime": 350.0}


def test_save_progress_quotes_the_item_id(shelf, abs_transport):
    abs_transport.responses["/api/me/progress/..%2Fsecret"] = None
    shelf.save_progress("../secret", 1.0, None)
    assert abs_transport.requests[0]["path"] == "/api/me/progress/..%2Fsecret"


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


def test_the_wire_sends_a_write_as_json_and_reads_no_reply(monkeypatch):
    # Audiobookshelf answers a progress PATCH with a bare «OK», which is not
    # JSON: a write reads no body, or every save would look like a server
    # that is not an Audiobookshelf.
    sent = []

    def urlopen(request, timeout):
        sent.append(request)
        return _Response(b"OK")

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    assert audiobookshelf.call(BASE, KEY, {
        "path": "/api/me/progress/li-1", "method": "PATCH",
        "body": {"currentTime": 12.5}}, 1.0) is None
    request = sent[0]
    assert request.get_method() == "PATCH"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {"currentTime": 12.5}


@pytest.mark.parametrize("code, words", [(401, "refused the API key"),
                                         (404, "no such item")])
def test_a_refusal_is_named_in_the_error(monkeypatch, code, words):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "no", {}, None)

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfError, match=words):
        audiobookshelf.call(BASE, KEY, {"path": "/api/items/x"}, 1.0)


def test_a_refusal_carries_its_status_code(monkeypatch):
    # progress() tells "never started" (404) from any other refusal by this
    # alone, so the status has to survive the trip up from the wire.
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "no", {}, None)

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfError) as exc:
        audiobookshelf.call(BASE, KEY, {"path": "/api/items/x"}, 1.0)
    assert exc.value.status == 404


def test_an_unreachable_server_is_an_error_not_a_crash(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfError, match="not answering"):
        audiobookshelf.call(BASE, KEY, {"path": "/api/libraries"}, 1.0)


def test_a_body_that_is_not_json_is_an_error(monkeypatch):
    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen",
                        lambda request, timeout: _Response(b"<html>login</html>"))
    with pytest.raises(AudiobookshelfError, match="not JSON"):
        audiobookshelf.call(BASE, KEY, {"path": "/api/libraries"}, 1.0)


# -- silence and refusal are not the same thing --------------------------------

@pytest.mark.parametrize("code, kind", [
    (401, AudiobookshelfRefused), (403, AudiobookshelfRefused),
    (404, AudiobookshelfRefused), (502, AudiobookshelfUnreachable),
    (504, AudiobookshelfUnreachable),
])
def test_an_error_status_is_an_answer_unless_a_gateway_sent_it(monkeypatch,
                                                               code, kind):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "no", {}, None)

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(kind):
        audiobookshelf.call(BASE, KEY, {"path": "/api/libraries"}, 1.0)


def test_a_refused_connection_never_reached_the_shelf(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError(111, "no"))

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfUnreachable) as exc:
        audiobookshelf.call(BASE, KEY, {"path": "/api/libraries"}, 1.0)
    assert exc.value.delivered is False


def test_a_timeout_may_have_been_delivered(monkeypatch):
    # Not a certainty either way, so the cautious reading: the request may
    # have been carried out, and only what is safe to repeat is repeated.
    def urlopen(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(audiobookshelf.urllib.request, "urlopen", urlopen)
    with pytest.raises(AudiobookshelfUnreachable) as exc:
        audiobookshelf.call(BASE, KEY, {"path": "/api/libraries"}, 1.0)
    assert exc.value.delivered is True


def test_an_expired_key_does_not_shut_the_breaker_on_the_shelf(shelf):
    """The whole point of the two kinds: a key that expired answers 401, and
    three of those used to stop the client dialling for fifteen seconds — so
    a shelf that is plainly awake became "not answering" for every request
    after the third.
    """
    calls = []

    def refusing(request):
        calls.append(request)
        raise AudiobookshelfRefused("Audiobookshelf refused the API key")

    shelf._transport = refusing
    for _ in range(5):
        with pytest.raises(AudiobookshelfError):
            shelf.book_libraries()
    assert shelf._breaker.open_for() == 0
    assert len(calls) == 5      # each one asked once, and never twice


def test_every_request_a_shelf_makes_is_safe_to_repeat(shelf):
    # A GET of the catalogue and nothing else, so a lost reply is worth
    # asking about again — see AudiobookshelfClient._repeat_safe.
    for path in ("/api/libraries", "/api/libraries/lib-a/search",
                 "/api/items/abc"):
        assert shelf._repeat_safe({"path": path, "query": {}}) is True


def test_a_lost_reply_is_asked_for_again(shelf):
    """And the retry is the reason it matters: one dropped packet on a
    read-only GET must not become «l'impianto non risponde».
    """
    calls = []
    libraries = LIBRARIES

    def flaky(request):
        calls.append(request)
        if len(calls) == 1:
            raise AudiobookshelfUnreachable("dropped")
        return libraries

    shelf._transport = flaky
    assert shelf.book_libraries()
    assert len(calls) == 2



# -- a 200 that is not the object the API documents ----------------------------
#
# ``call()`` turns a body that is not JSON into an AudiobookshelfRefused, and
# let a body that IS valid JSON but not an object straight through: a captive
# portal or a reverse-proxy error page rendered as a JSON array or string, or
# a schema that moved. Three frames up that became
# ``AttributeError: 'list' object has no attribute 'get'`` — which is not a
# PlayerError, so ``spoken_library.open_library`` does not catch it and the
# whole voice assistant refuses to start over a bookshelf. The music has
# nothing to do with the books; that is the promise this file's docstring and
# the changelog both make.

@pytest.mark.parametrize("body", [[], ["nope"], "hello", 5, True])
def test_a_reply_that_is_not_an_object_is_a_player_error(abs_transport, body):
    # The EMPTY list is in here on purpose. It is tempting to read it as
    # "no shelves" and carry on, and that would be a guess: this endpoint
    # answers `{"libraries": [...]}` and says "none" with an empty list
    # INSIDE that object. A bare `[]` is the same fact as `["nope"]` — the
    # thing that replied is not an Audiobookshelf — and guessing otherwise
    # would turn a misconfigured URL into a silent empty bookshelf.
    abs_transport.responses["/api/libraries"] = body
    client = AudiobookshelfClient(BASE, KEY, transport=abs_transport)
    with pytest.raises(PlayerError):
        client.book_libraries()


@pytest.mark.parametrize("rows", [["nope"], [None], [5]])
def test_a_shelf_that_is_not_an_object_is_skipped(abs_transport, rows):
    # The envelope is right and a row inside it is not. One bad row must not
    # take the shelves that are fine with it.
    abs_transport.responses["/api/libraries"] = {
        "libraries": rows + [{"id": "ok", "name": "Audiolibri",
                              "mediaType": "book"}]}
    client = AudiobookshelfClient(BASE, KEY, transport=abs_transport)
    assert client.book_libraries() == [{"id": "ok", "name": "Audiolibri"}]


def test_a_track_row_that_is_not_an_object_is_skipped(abs_transport):
    abs_transport.responses["/api/items/b1"] = {
        "media": {"tracks": ["nope", {"contentUrl": "/s/1.m4b"}, None]}}
    client = AudiobookshelfClient(BASE, KEY, transport=abs_transport)
    urls = client.stream_urls("b1")
    assert len(urls) == 1 and urls[0].startswith(BASE + "/s/1.m4b?")


def test_a_media_block_that_is_not_an_object_is_no_audio(abs_transport):
    abs_transport.responses["/api/items/b1"] = {"media": "gone"}
    client = AudiobookshelfClient(BASE, KEY, transport=abs_transport)
    assert client.stream_urls("b1") == []


def test_a_duration_that_is_not_a_number_does_not_escape(abs_transport):
    # float("soon") is a ValueError, which is not a PlayerError either — same
    # failure, one layer in.
    abs_transport.responses["/api/libraries"] = {
        "libraries": [{"id": "l1", "name": "Audiolibri", "mediaType": "book"}]}
    abs_transport.responses["/api/libraries/l1/search"] = {
        "book": [{"libraryItem": {"id": "b1", "media": {
            "duration": "soon", "tracks": [{"contentUrl": "/s/1.m4b"}],
            "metadata": {"title": "Il Nome della Rosa"}}}}]}
    client = AudiobookshelfClient(BASE, KEY, transport=abs_transport)
    found = client.book_candidates("rosa")
    assert [b["title"] for b in found] == ["Il Nome della Rosa"]
    assert found[0]["duration"] == 0.0
