"""Now-playing: the ``status_info()`` engine query and the web endpoints.

``/nowplaying`` must answer 200 with ``mode: unknown`` when the LMS is down
(the panel hides; no error spam), and ``/artwork`` is a server-side proxy —
the page is HTTPS while the LMS is HTTP, so a direct <img> would be blocked
as mixed content. The proxy derives the artwork URL from the player status
itself (no client-supplied URL = no open relay).
"""

import urllib.error

import pytest


# -- status_info() ------------------------------------------------------------

def test_status_info_local_track_uses_coverid(lms, transport):
    transport.responses["status"] = {
        "mode": "play", "time": 42.5,
        "playlist_loop": [{"title": "Time", "artist": "Pink Floyd",
                           "album": "The Dark Side of the Moon",
                           "coverid": "ab12cd", "duration": 421}],
    }
    info = lms.status_info()
    assert info["mode"] == "play"
    assert info["title"] == "Time"
    assert info["artist"] == "Pink Floyd"
    assert info["album"] == "The Dark Side of the Moon"
    assert info["elapsed"] == 42.5
    assert info["duration"] == 421
    assert info["artwork"] == "/music/ab12cd/cover.jpg"


def test_status_info_remote_track_keeps_absolute_artwork_url(lms, transport):
    transport.responses["status"] = {
        "mode": "play",
        "playlist_loop": [{"title": "Song", "artist": "X",
                           "artwork_url": "https://images.example/cover.jpg"}],
    }
    assert lms.status_info()["artwork"] == "https://images.example/cover.jpg"


def test_status_info_relative_artwork_url_gets_leading_slash(lms, transport):
    transport.responses["status"] = {
        "mode": "play",
        "playlist_loop": [{"title": "Song",
                           "artwork_url": "imageproxy/abc/image.jpg"}],
    }
    assert lms.status_info()["artwork"] == "/imageproxy/abc/image.jpg"


def test_status_info_track_without_cover_falls_back_to_current(lms, transport):
    transport.responses["status"] = {
        "mode": "pause",
        "playlist_loop": [{"title": "Song"}],
    }
    info = lms.status_info()
    assert info["mode"] == "pause"
    assert info["artwork"] == "/music/current/cover.jpg?player=aa:bb:cc:dd:ee:ff"


def test_status_info_empty_playlist(lms, transport):
    transport.responses["status"] = {"mode": "stop"}
    info = lms.status_info()
    assert info["mode"] == "stop"
    assert info["title"] is None
    assert info["artwork"] is None

# -- HTTP endpoints -----------------------------------------------------------

class FakeArtworkFetch:
    def __init__(self):
        self.urls = []

    def __call__(self, url, timeout=5.0):
        self.urls.append(url)
        return "image/png", b"PNGDATA"


@pytest.fixture
def http_server(live_server):
    """The real handler with an injectable artwork fetch."""
    fetch = FakeArtworkFetch()
    yield live_server(artwork_fetch=fetch), fetch


def test_nowplaying_endpoint(http_server, transport):
    srv, _ = http_server
    transport.responses["status"] = {
        "mode": "play", "time": 10,
        "playlist_loop": [{"title": "Time", "artist": "Pink Floyd",
                           "coverid": "ab12cd", "duration": 421}],
    }
    resp = srv.get("/nowplaying")
    assert resp.status == 200
    assert resp.json()["title"] == "Time"
    # The client never sees the LMS URL: artwork points back at the proxy,
    # with a per-track cache-buster.
    assert resp.json()["artwork"].startswith("/artwork?v=")


def test_nowplaying_lms_down_answers_unknown_not_500(http_server, transport):
    srv, _ = http_server
    transport.raise_on.add("status")
    resp = srv.get("/nowplaying")
    assert resp.status == 200
    assert resp.json() == {"mode": "unknown"}


def test_artwork_proxies_lms_relative_path(http_server, transport):
    srv, fetch = http_server
    transport.responses["status"] = {
        "mode": "play",
        "playlist_loop": [{"title": "Time", "coverid": "ab12cd"}],
    }
    resp = srv.get("/artwork?v=1")
    assert resp.status == 200
    assert resp.body == b"PNGDATA"
    assert resp.headers["Content-Type"] == "image/png"
    assert resp.headers["Cache-Control"] == "no-store"
    assert fetch.urls == ["http://lms.local:9000/music/ab12cd/cover.jpg"]


def test_artwork_proxies_absolute_plugin_url(http_server, transport):
    srv, fetch = http_server
    transport.responses["status"] = {
        "mode": "play",
        "playlist_loop": [{"title": "Song",
                           "artwork_url": "https://images.example/c.jpg"}],
    }
    srv.get("/artwork")
    assert fetch.urls == ["https://images.example/c.jpg"]


def test_artwork_404_when_nothing_plays(http_server, transport):
    srv, _ = http_server
    transport.responses["status"] = {"mode": "stop"}
    with pytest.raises(urllib.error.HTTPError) as exc:
        srv.get("/artwork")
    assert exc.value.code == 404


# -- an audiobook of ours (T5.6) ------------------------------------------------
#
# The player knows only the file: a remote URL whose tag is a chapter's name,
# no book, no author, no picture. The Composite knows the rest, and the panel
# shows that instead — only while the book is ours (Composite.now_playing).

class Books:
    """What the web server asks of a Composite: ``now_playing(client)``."""

    def __init__(self, answer=None, error=None):
        self.answer, self.error = answer, error
        self.asked = []

    def now_playing(self, client):
        self.asked.append(client.player_id)
        if self.error:
            raise self.error
        return self.answer


FAVOLE = {"title": "Le favole di La Fontaine", "author": "Jean de La Fontaine",
          "chapter": 3, "chapters": 9, "chapter_title": "Il Castaldo",
          "cover": "http://abs.local:13378/api/items/b1/cover?token=k"}

A_FILE = {"mode": "play", "time": 12,
          "playlist_loop": [{"title": "03 - Il Castaldo, il Cane e la V",
                             "duration": 222,
                             "url": "http://abs.local:13378/api/items/b1/file/3"}]}


def test_a_book_of_ours_shows_the_book_the_author_and_the_chapter(live_server,
                                                                  transport):
    transport.responses["status"] = A_FILE
    srv = live_server(artwork_fetch=FakeArtworkFetch(), books=Books(FAVOLE))
    info = srv.json_get("/nowplaying")
    assert info["title"] == "Le favole di La Fontaine"
    assert info["artist"] == "Jean de La Fontaine"
    assert (info["chapter"], info["chapters"], info["chapter_title"]) == (
        3, 9, "Il Castaldo")
    assert info["artwork"].startswith("/artwork?v=")
    # The player's own state is still the player's: the panel's controls
    # read these.
    assert (info["mode"], info["elapsed"], info["duration"]) == ("play", 12, 222)


def test_the_cover_is_the_books_fetched_by_the_proxy(live_server, transport):
    transport.responses["status"] = A_FILE
    fetch = FakeArtworkFetch()
    srv = live_server(artwork_fetch=fetch, books=Books(FAVOLE))
    assert srv.get("/artwork?v=1").status == 200
    assert fetch.urls == [FAVOLE["cover"]]


def test_a_book_with_no_title_keeps_what_the_player_says(live_server, transport):
    transport.responses["status"] = A_FILE
    answer = dict(FAVOLE, title="", author="", cover=None)
    srv = live_server(artwork_fetch=FakeArtworkFetch(), books=Books(answer))
    info = srv.json_get("/nowplaying")
    assert info["title"] == "03 - Il Castaldo, il Cane e la V"
    assert info["chapter"] == 3


@pytest.mark.parametrize("books", [Books(None), Books(error=RuntimeError("off"))])
def test_music_or_a_failing_shelf_is_shown_as_the_player_says(live_server,
                                                              transport, books):
    # Not ours (None), or the shelf down: the panel is the player's, as for
    # any record — a bookshelf never costs the panel its music.
    transport.responses["status"] = {
        "mode": "play", "playlist_loop": [{"title": "Time", "artist": "Pink Floyd",
                                           "coverid": "ab12cd"}]}
    fetch = FakeArtworkFetch()
    srv = live_server(artwork_fetch=fetch, books=books)
    info = srv.json_get("/nowplaying")
    assert (info["title"], info["artist"]) == ("Time", "Pink Floyd")
    assert "chapter" not in info
    srv.get("/artwork")
    assert fetch.urls == ["http://lms.local:9000/music/ab12cd/cover.jpg"]


# -- /player (mini-player transport) ------------------------------------------

PLAYING = {
    "mode": "play", "time": 10,
    "playlist_loop": [{"title": "Time", "artist": "Pink Floyd",
                       "coverid": "ab12cd", "duration": 421}],
}


@pytest.mark.parametrize(
    "payload, expected_cmd",
    [
        ({"action": "pause"}, ["pause", "1"]),
        ({"action": "resume"}, ["pause", "0"]),
        ({"action": "next"}, ["playlist", "index", "+1"]),
        ({"action": "prev"}, ["playlist", "index", "-1"]),
        ({"action": "seek", "seconds": 93.7}, ["time", "93"]),
        ({"action": "seek", "seconds": -4}, ["time", "0"]),
    ],
)
def test_player_actions_reach_the_lms(http_server, transport, payload,
                                      expected_cmd):
    srv, _ = http_server
    transport.responses["status"] = PLAYING
    resp = srv.post_json("/player", payload)
    data = resp.json()
    assert resp.status == 200
    assert data["ok"] is True
    assert expected_cmd in transport.commands()
    # The reply carries the fresh status so the UI syncs without re-polling,
    # artwork rewritten to the proxy like /nowplaying.
    assert data["title"] == "Time"
    assert data["artwork"].startswith("/artwork?v=")


def test_player_unknown_action_is_refused(http_server, transport):
    srv, _ = http_server
    transport.responses["status"] = PLAYING
    resp = srv.post_json("/player", {"action": "explode"})
    assert resp.status == 200
    assert resp.json() == {"ok": False, "error": "unknown_action"}
    assert transport.commands() == []  # nothing reached the LMS


def test_player_lms_down_answers_200_not_500(http_server, transport):
    srv, _ = http_server
    transport.raise_on.add("pause")
    resp = srv.post_json("/player", {"action": "pause"})
    assert resp.status == 200
    assert resp.json()["ok"] is False


def test_player_garbage_body_is_refused(http_server, transport):
    srv, _ = http_server
    resp = srv.post("/player", data=b"not json")
    assert resp.json()["ok"] is False
