"""Router-level coverage for T2.1 (queue management) and T2.2 (favorites &
radio): IT+EN phrasing, source resolution, multi-room, and — the one thing
that can't be tested at the actions.py layer — that picking from a list a
queue command opened ("aggiungi X alla coda" -> "did you mean" -> "la 2")
queues the pick instead of interrupting playback, while a list opened by an
ordinary command still plays as before.
"""

import pytest

from conftest import FakeLicense
from pro.multiroom import MultiRoom
from router import Router

PLAYERS = [
    {"playerid": "aa:aa", "name": "Salotto"},
    {"playerid": "bb:bb", "name": "Cucina"},
]


@pytest.fixture
def router(lms):
    return Router(lms)


@pytest.fixture
def room_router(lms):
    return Router(lms, multiroom=MultiRoom(FakeLicense(pro=True), lambda: PLAYERS))


# -- queue: add / insert -----------------------------------------------------

def test_queue_add_it(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    reply = router.handle("aggiungi Time alla coda", source="tidal")
    assert str(reply) == "Ho aggiunto Time alla coda da TIDAL."
    assert ["playlist", "add", "tidal://1.flc"] in transport.commands()


def test_queue_insert_it(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    reply = router.handle("metti Time dopo questa", source="tidal")
    assert str(reply) == "Metto Time subito dopo questa da TIDAL."
    assert ["playlist", "insert", "tidal://1.flc"] in transport.commands()


def test_queue_add_en(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    reply = router.handle("add Time to the queue", lang="en", source="tidal")
    assert str(reply) == "Added Time to the queue from TIDAL."
    assert ["playlist", "add", "tidal://1.flc"] in transport.commands()


def test_queue_insert_en(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    reply = router.handle("play Time next", lang="en", source="tidal")
    assert str(reply) == "I'll play Time right after this one from TIDAL."


def test_queue_add_local_source(router, transport):
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {
        "titles_loop": [{"id": 5, "title": "Fragile"}]
    }
    reply = router.handle("aggiungi Fragile alla coda", source="local")
    assert str(reply) == "Ho aggiunto Fragile alla coda dalla tua musica."
    assert ["playlistcontrol", "cmd:add", "track_id:5"] in transport.commands()


def test_queue_add_does_not_get_swallowed_by_generic_play(router, transport):
    # Before this feature, "aggiungi" wasn't a play verb at all: the phrase
    # fell through to the fallback. It must not become a generic play query
    # with "alla coda" polluting the title either.
    reply = router.handle("aggiungi Time alla coda", source="tidal")
    assert not str(reply).startswith("Non ho capito")


# -- queue: clear / list ------------------------------------------------------

def test_queue_clear_it(router, transport):
    reply = router.handle("svuota la coda")
    assert str(reply) == "Coda svuotata."
    assert ["playlist", "clear"] in transport.commands()


def test_queue_clear_en(router, transport):
    reply = router.handle("clear the queue", lang="en")
    assert str(reply) == "Queue cleared."


def test_queue_list_it(router, transport):
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Now"}, {"title": "Next", "artist": "X"}]
    }
    reply = router.handle("cosa c'è in coda")
    assert str(reply) == "In coda: 1: Next di X."


def test_queue_list_en(router, transport):
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Now"}, {"title": "Next", "artist": "X"}]
    }
    reply = router.handle("what's in the queue", lang="en")
    assert str(reply) == "Coming up: 1: Next by X."


def test_queue_list_does_not_clash_with_nowplaying(router, transport):
    # "cosa c'è in coda" must not be swallowed by the (cosa|che) nowplaying
    # pattern — it requires suona/canzone/ascolt nearby, which this lacks.
    transport.responses["status"] = {"playlist_loop": [{"title": "Now"}]}
    reply = router.handle("cosa c'è in coda")
    assert str(reply) == "La coda è vuota."


# -- favorites & radio ---------------------------------------------------------

def test_favorites_it(router, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "1", "name": "Radio Paradise"}]}
    )
    reply = router.handle("riproduci i preferiti")
    assert str(reply) == "Riproduco i preferiti."
    assert ["favorites", "playlist", "play", "item_id:1"] in transport.commands()


def test_favorites_en(router, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "1", "name": "Radio Paradise"}]}
    )
    reply = router.handle("play my favorites", lang="en")
    assert str(reply) == "Playing your favorites."


def test_radio_it(router, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "3", "name": "Radio Paradise"}]}
    )
    reply = router.handle("metti la radio Radio Paradise")
    assert str(reply) == "Metto la radio Radio Paradise."


def test_radio_en(router, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "3", "name": "Radio Paradise"}]}
    )
    reply = router.handle("play the radio Radio Paradise", lang="en")
    assert str(reply) == "Playing the radio station Radio Paradise."


def test_radio_missing_plugin_is_honest(router, transport):
    transport.responses["favorites"] = {"loop_loop": []}
    reply = router.handle("metti la radio Jazz FM")
    assert str(reply) == (
        "Non ho trovato una radio chiamata Jazz FM tra i tuoi preferiti.")


# -- a queue-opened list is picked in queue mode, not played -------------------

def test_pick_from_queue_add_list_queues_not_plays(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc",
             "name": "Another Brick in the Wall, Pt. 1"},
            {"isaudio": 1, "url": "tidal://2.flc",
             "name": "Another Brick in the Wall, Pt. 2"},
        ]},
    )
    router.handle("aggiungi brick alla coda", source="tidal")
    reply = router.handle("metti la 2")
    assert "aggiunto" in str(reply)
    assert ["playlist", "add", "tidal://2.flc"] in transport.commands()
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_pick_from_queue_insert_list_by_name(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc",
             "name": "Another Brick in the Wall, Pt. 1"},
            {"isaudio": 1, "url": "tidal://2.flc",
             "name": "Another Brick in the Wall, Pt. 2"},
        ]},
    )
    router.handle("metti brick dopo questa", source="tidal")
    reply = router.handle("Another Brick in the Wall, Pt. 2")
    assert "subito dopo questa" in str(reply)
    assert ["playlist", "insert", "tidal://2.flc"] in transport.commands()


def test_a_fresh_play_list_still_plays_after_a_queue_pick(router, transport, make_tidal):
    # cand_mode must not leak from one list to the next: a normal listing
    # command re-opens the list in 'play' mode even right after a queue op.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc", "name": "Brick 1"},
            {"isaudio": 1, "url": "tidal://2.flc", "name": "Brick 2"},
        ]},
    )
    router.handle("aggiungi brick alla coda", source="tidal")
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = {"albums_loop": [{"id": 9, "album": "Fragile"}]}
    router.handle("quali album ho di Yes")
    reply = router.handle("metti la 1")
    assert ["playlistcontrol", "cmd:load", "album_id:9"] in transport.commands()
    assert "Riproduco" in str(reply)


# -- multi-room ----------------------------------------------------------------

def test_queue_add_targets_the_named_room(room_router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    reply = room_router.handle("aggiungi Time alla coda in cucina", source="tidal")
    assert ("bb:bb", ["playlist", "add", "tidal://1.flc"]) in transport.calls
    assert "Cucina" in str(reply)


def test_favorites_targets_the_named_room(room_router, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "1", "name": "Radio Paradise"}]}
    )
    room_router.handle("riproduci i preferiti in cucina")
    assert ("bb:bb", ["favorites", "playlist", "play", "item_id:1"]) in transport.calls


# -- regression: transport words in a queued title must not hijack the intent -

def test_queue_add_with_a_transport_word_title_is_not_hijacked(router, transport, make_tidal):
    # "aggiungi" isn't a play verb, so is_play stays False for this phrase;
    # the transport checks (pause/resume/next/prev) used to run BEFORE the
    # queue patterns and "Stop" collided with the pause pattern, turning a
    # queue-add into a pause with the LMS never touched for the title at all.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Stop"}]},
    )
    reply = router.handle("aggiungi Stop alla coda", source="tidal")
    assert str(reply) == "Ho aggiunto Stop alla coda da TIDAL."
    assert ["playlist", "add", "tidal://1.flc"] in transport.commands()
    assert ["pause", "1"] not in transport.commands()


def test_queue_insert_with_a_transport_word_title_is_not_hijacked(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Next"}]},
    )
    reply = router.handle("metti Next dopo questa", source="tidal")
    assert str(reply) == "Metto Next subito dopo questa da TIDAL."
    assert ["playlist", "insert", "tidal://1.flc"] in transport.commands()
    assert ["playlist", "index", "+1"] not in transport.commands()


# -- regression: "cosa c'è in coda" must respect the kid-safe blocklist -------

def test_queue_list_hides_blocked_titles(lms, transport, tmp_path):
    from pro.kidsafe import KidSafe

    kidsafe = KidSafe(str(tmp_path), FakeLicense(pro=True))
    kidsafe.enable("1234", "owner")  # unlocked only for "owner", not "kid"
    kidsafe.store.put(["Bad Song"])

    r = Router(lms, kidsafe=kidsafe, client_id="kid")
    transport.responses["status"] = {
        "playlist_loop": [
            {"title": "Now Playing"},
            {"title": "Bad Song", "artist": "X"},
            {"title": "Good Song", "artist": "Y"},
        ]
    }
    reply = r.handle("cosa c'è in coda")
    assert "Bad Song" not in str(reply)
    assert "Good Song" in str(reply)
