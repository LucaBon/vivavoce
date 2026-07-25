"""Tests for the queue semantics (P2): add to queue / play next / shuffle /
repeat — Alexa-style queue handling, replacing nothing that's playing."""

import pytest

import actions
from router import Router


@pytest.fixture
def router(lms):
    return Router(lms)


def _tidal_time(transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )


# -- add to queue (streaming) ----------------------------------------------
@pytest.mark.parametrize("phrase", ["aggiungi Time alla coda",
                                    "metti in coda Time",
                                    "metti Time in coda"])
def test_queue_add_it(router, transport, make_tidal, phrase):
    _tidal_time(transport, make_tidal)
    assert router.handle(phrase, source="tidal") == (
        "Ho aggiunto Time alla coda da TIDAL."
    )
    assert ["playlist", "add", "tidal://1.flc"] in transport.commands()
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


@pytest.mark.parametrize("phrase", ["queue up Time", "queue Time",
                                    "add Time to the queue"])
def test_queue_add_en(router, transport, make_tidal, phrase):
    _tidal_time(transport, make_tidal)
    assert router.handle(phrase, source="tidal", lang="en") == (
        "Added Time to the queue from TIDAL."
    )
    assert ["playlist", "add", "tidal://1.flc"] in transport.commands()


# -- play next (insert after current) --------------------------------------
@pytest.mark.parametrize("phrase", ["metti Time subito dopo",
                                    "dopo questa metti Time"])
def test_queue_next_it(router, transport, make_tidal, phrase):
    _tidal_time(transport, make_tidal)
    assert router.handle(phrase, source="tidal") == (
        "Va bene, dopo questa metto Time da TIDAL."
    )
    assert ["playlist", "insert", "tidal://1.flc"] in transport.commands()


@pytest.mark.parametrize("phrase", ["play Time next", "after this play Time"])
def test_queue_next_en(router, transport, make_tidal, phrase):
    _tidal_time(transport, make_tidal)
    assert router.handle(phrase, source="tidal", lang="en") == (
        "Okay, playing Time after this one from TIDAL."
    )
    assert ["playlist", "insert", "tidal://1.flc"] in transport.commands()


# -- queue picks the right track, like play does ---------------------------
def test_queue_prefers_exact_title(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc", "name": "Money for Nothing"},
            {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"},
        ]},
    )
    router.handle("aggiungi Money alla coda", source="tidal")
    assert ["playlist", "add", "tidal://2.flc"] in transport.commands()


def test_queue_honors_named_artist(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc", "name": "Comfortably Numb",
             "artist": "The Australian Pink Floyd Show"},
            {"isaudio": 1, "url": "tidal://2.flc", "name": "Comfortably Numb",
             "artist": "Pink Floyd"},
        ]},
    )
    router.handle("aggiungi Comfortably Numb dei Pink Floyd alla coda",
                  source="tidal")
    assert ["playlist", "add", "tidal://2.flc"] in transport.commands()


# -- local library queueing -------------------------------------------------
def test_queue_local(router, transport):
    transport.responses["titles"] = {
        "titles_loop": [{"id": 3, "title": "Time"}]
    }
    assert router.handle("aggiungi Time alla coda", source="local") == (
        "Ho aggiunto Time alla coda."
    )
    assert ["playlistcontrol", "cmd:add", "track_id:3"] in transport.commands()


def test_queue_local_next_inserts(router, transport):
    transport.responses["titles"] = {
        "titles_loop": [{"id": 3, "title": "Time"}]
    }
    router.handle("metti Time subito dopo", source="local")
    assert ["playlistcontrol", "cmd:insert", "track_id:3"] in transport.commands()


def test_queue_auto_falls_back_to_streaming(router, transport, make_tidal):
    transport.responses["titles"] = {"count": 0}
    _tidal_time(transport, make_tidal)
    assert router.handle("aggiungi Time alla coda", source="auto") == (
        "Ho aggiunto Time alla coda da TIDAL."
    )
    assert ["playlist", "add", "tidal://1.flc"] in transport.commands()


def test_queue_local_rejects_loose_match(router, transport):
    # A loose local row must not be queued (same policy as play_local).
    transport.responses["titles"] = {
        "titles_loop": [{"id": 9, "title": "Be My Lover"}]
    }
    res = actions.queue_local(router.lms, "love")
    assert res.ok is False
    assert not any(c[0] == "playlistcontrol" for c in transport.commands())


# -- blocked content --------------------------------------------------------
def test_queue_blocked_for_restricted_speaker(lms, transport, make_tidal):
    _tidal_time(transport, make_tidal)
    guard = actions.Guard(restricted=True, blocklist=["Time"])
    res = actions.queue_song(lms, "Time", guard=guard)
    assert res.ok is False and res == actions.BLOCKED_SPEECH
    assert not any(c[:2] == ["playlist", "add"] for c in transport.commands())


# -- shuffle / repeat --------------------------------------------------------
@pytest.mark.parametrize("phrase, lang, cmd", [
    ("shuffle", "it", ["playlist", "shuffle", "1"]),
    ("attiva la riproduzione casuale", "it", ["playlist", "shuffle", "1"]),
    ("mescola tutto", "it", ["playlist", "shuffle", "1"]),
    ("disattiva lo shuffle", "it", ["playlist", "shuffle", "0"]),
    ("attiva la ripetizione", "it", ["playlist", "repeat", "2"]),
    ("ripeti tutto", "it", ["playlist", "repeat", "2"]),
    ("disattiva la ripetizione", "it", ["playlist", "repeat", "0"]),
    ("shuffle", "en", ["playlist", "shuffle", "1"]),
    ("turn on shuffle", "en", ["playlist", "shuffle", "1"]),
    ("shuffle off", "en", ["playlist", "shuffle", "0"]),
    ("repeat", "en", ["playlist", "repeat", "2"]),
    ("turn off repeat", "en", ["playlist", "repeat", "0"]),
])
def test_shuffle_repeat_phrases(router, transport, phrase, lang, cmd):
    router.handle(phrase, lang=lang)
    assert transport.last_call()[1] == cmd


def test_title_containing_queue_word_still_plays(router, transport, make_tidal):
    # Anchored patterns: a play whose title mentions "coda" is not a queue op.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://8.flc",
                      "name": "La coda del diavolo"}]},
    )
    assert router.handle("metti la coda del diavolo", source="tidal") == (
        "Riproduco La coda del diavolo da TIDAL."
    )
    assert ["playlist", "play", "tidal://8.flc"] in transport.commands()
    assert not any(c[:2] == ["playlist", "add"] for c in transport.commands())
