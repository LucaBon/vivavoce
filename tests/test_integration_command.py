"""End-to-end: a spoken phrase over HTTP all the way to an LMS command.

Everything else tests one layer with the next one faked. These drive the whole
stack for real — ``POST /command`` -> ``Router`` -> ``actions`` -> ``LMSClient``
-> the fake JSON-RPC transport — and assert on the commands the LMS actually
received, not just on the sentence the user hears. A layer wired up wrongly
still returns plausible speech; only the command list proves the music plays.

Two things here cannot be tested any other way:

* **list state across requests.** "metti la 2" only works if the router that
  read out the list is the same object that handles the next, separate HTTP
  request. That is what the keyed ``routers`` dict in ``server.py`` is for, and
  it takes two real requests to prove.
* **the never-500 guarantee.** A traceback escaping ``do_POST`` would leave the
  page with an unparseable body and no way to recover.
"""

from conftest import FakeLicense

YES_ALBUMS = {"albums_loop": [{"id": 345, "album": "90125"},
                              {"id": 9, "album": "Fragile"}]}


def _nothing_local(transport):
    """No local library hits, so 'auto' falls through to the streaming service."""
    for name in ("albums", "artists", "titles"):
        transport.responses[name] = {"count": 0}


# -- the happy paths -----------------------------------------------------------

def test_local_album_plays_over_http(live_server, transport):
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]
    }
    reply = live_server().json_post("/command", {"text": "riproduci 90125",
                                                 "client": "phone"})
    assert reply["ok"] is True
    assert "90125" in reply["speech"]
    # The point of the test: the LMS was actually told to load that album.
    assert ["playlistcontrol", "cmd:load", "album_id:345"] in transport.commands()


def test_streaming_track_plays_over_http(live_server, transport, make_feed):
    _nothing_local(transport)
    transport.responses["tidal"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    reply = live_server().json_post("/command", {"text": "riproduci Time",
                                                 "client": "phone"})
    assert reply["ok"] is True
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_transport_command_reaches_the_lms(live_server, transport):
    reply = live_server().json_post("/command", {"text": "pausa",
                                                 "client": "phone"})
    assert reply["ok"] is True
    assert ["pause", "1"] in transport.commands()


# -- conversation state across separate requests -------------------------------

def test_list_then_pick_spans_two_requests(live_server, transport):
    # The whole point of keying a Router per client: the numbered list read out
    # in one request has to still be there for the next one.
    srv = live_server()
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = YES_ALBUMS

    listing = srv.json_post("/command", {"text": "quali album ho di Yes",
                                         "client": "phone"})
    assert "1: 90125" in listing["speech"]

    pick = srv.json_post("/command", {"text": "metti la 2", "client": "phone"})
    assert pick["ok"] is True
    assert ["playlistcontrol", "cmd:load", "album_id:9"] in transport.commands()


def test_two_clients_keep_separate_lists(live_server, transport):
    # Two phones must not clobber each other's "metti la N". A fresh library
    # search answers with a different id than the read-out list, so the id that
    # gets loaded says which path was taken.
    def albums(cmd):
        if any(str(p).startswith("artist_id:") for p in cmd):  # the read-out list
            return YES_ALBUMS
        return {"albums_loop": [{"id": 999, "album": "Something Else"}]}

    srv = live_server()
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = albums

    srv.json_post("/command", {"text": "quali album ho di Yes",
                               "client": "kitchen"})
    # The second phone never saw that list, so it cannot pick from it.
    srv.json_post("/command", {"text": "metti la 2", "client": "study"})
    assert ["playlistcontrol", "cmd:load", "album_id:9"] not in transport.commands()

    # ...while the phone that did see it still picks the second entry.
    picked = srv.json_post("/command", {"text": "metti la 2",
                                        "client": "kitchen"})
    assert picked["ok"] is True
    assert ["playlistcontrol", "cmd:load", "album_id:9"] in transport.commands()


def test_choices_are_returned_for_the_ui(live_server, transport):
    # The page renders the read-out list as tappable buttons.
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = YES_ALBUMS
    reply = live_server().json_post("/command",
                                    {"text": "quali album ho di Yes",
                                     "client": "phone"})
    assert [(c["n"], c["label"]) for c in reply["choices"]] == [
        (1, "90125"), (2, "Fragile")]


# -- language ------------------------------------------------------------------

def test_english_command_answers_in_english(live_server, transport):
    # Safe to leave the process in English: conftest resets the language.
    reply = live_server().json_post("/command", {"text": "pause",
                                                 "client": "phone",
                                                 "lang": "en"})
    assert reply["ok"] is True
    assert reply["speech"] == "Paused."
    assert ["pause", "1"] in transport.commands()


def test_language_does_not_leak_into_the_next_request(live_server, transport):
    srv = live_server()
    srv.json_post("/command", {"text": "pause", "client": "phone",
                               "lang": "en"})
    italian = srv.json_post("/command", {"text": "pausa", "client": "phone"})
    assert italian["speech"] == "In pausa."


def test_alternatives_let_a_later_guess_win(live_server, transport):
    # Web Speech mangles English titles; a lower-ranked alternative often gets
    # it right, and only a hit is allowed to play anything. The feed answers
    # the real search term, so the mangled guess genuinely finds nothing.
    _nothing_local(transport)
    track = {"isaudio": 1, "url": "tidal://7.flc", "name": "Bohemian Rhapsody"}

    def feed(cmd):
        if len(cmd) > 1 and cmd[1] == "playlist":   # the play action
            return {}
        params = cmd[2:]
        item_id = next((p[len("item_id:"):] for p in params
                        if p.startswith("item_id:")), None)
        search = next((p[len("search:"):] for p in params
                       if p.startswith("search:")), None)
        if item_id is None:
            return {"loop_loop": [{"id": "7", "type": "search", "name": "Search"}]}
        if search is not None:
            return {"loop_loop": [{"name": "Songs", "id": "S"}]}
        hit = "bohemian" in (feed.last_query or "").lower()
        return {"loop_loop": [track] if hit else []}

    feed.last_query = None

    def remember(cmd):
        for part in cmd[2:]:
            if part.startswith("search:"):
                feed.last_query = part[len("search:"):]
        return feed(cmd)

    transport.responses["tidal"] = remember
    srv = live_server()

    # The mangled guess on its own genuinely finds nothing — without this the
    # test below would pass even if the alternatives were ignored entirely.
    alone = srv.json_post("/command", {"text": "riproduci boemia napsodi",
                                       "client": "phone"})
    assert alone["ok"] is False
    assert transport.commands() == [] or not any(
        cmd[:2] == ["playlist", "play"] for cmd in transport.commands())

    reply = srv.json_post("/command", {
        "text": "riproduci boemia napsodi",
        "alternatives": ["riproduci boemia napsodi",
                         "riproduci Bohemian Rhapsody"],
        "client": "phone",
    })
    assert reply["ok"] is True
    assert reply["used"] == "riproduci Bohemian Rhapsody"
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()


# -- never a 5xx ---------------------------------------------------------------

def test_garbage_body_is_answered_not_crashed(live_server):
    resp = live_server().post("/command", data=b"not json at all")
    assert resp.status == 200
    assert resp.json()["ok"] is False


def test_empty_body_is_answered(live_server):
    resp = live_server().post("/command", data=b"")
    assert resp.status == 200
    assert resp.json()["ok"] is False


def test_lms_failure_is_answered_not_crashed(live_server, transport):
    transport.raise_on.add("pause")
    resp = live_server().post_json("/command", {"text": "pausa",
                                                "client": "phone"})
    assert resp.status == 200
    reply = resp.json()
    assert reply["ok"] is False
    assert reply["speech"]  # the user is told something, not left hanging


def test_missing_text_is_answered(live_server):
    reply = live_server().json_post("/command", {"client": "phone"})
    assert reply["ok"] is False


# -- /license over HTTP --------------------------------------------------------

def test_license_status_is_reported(live_server):
    assert live_server(license_mgr=FakeLicense(pro=True)).json_get(
        "/license") == {"pro": True}


def test_license_status_without_a_manager(live_server):
    assert live_server().json_get("/license") == {"pro": False}
