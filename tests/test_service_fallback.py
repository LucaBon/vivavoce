"""A streaming plugin that is installed but logged out.

This is what the failure actually looked like on a real Daphile: the TIDAL
plugin answered its whole menu with one item — «Please go to
Settings/Advanced/TIDAL to authenticate with TIDAL.» — so there was no search
node, every search came back empty, and «metti Comfortably Numb dei Pink
Floyd» was answered «Non ho trovato nessun brano». Two services on the same
server were logged in and had the song.

Two things follow, and this file is about both. A service the user did not
name can be swapped for one that can answer (``sources.SourceChoice``), and
what is left when none of them can answer is not a statement about the music.
"""

import pytest

import actions
from conftest import FakeLicense
from pro.kidsafe import KidSafe
from router import Router

# A logged-out plugin, verbatim in shape: one textarea, no search node.
LOGGED_OUT = {"loop_loop": [
    {"id": "7d9b13b4.0", "type": "textarea", "hasitems": 1,
     "name": "Please go to Settings/Advanced/TIDAL to authenticate with TIDAL."},
]}


@pytest.fixture
def router(lms):
    return Router(lms)


@pytest.fixture
def qobuz_has_the_song(transport, make_feed):
    """Qobuz logged in and holding Comfortably Numb; TIDAL logged out."""
    transport.responses["tidal"] = lambda cmd: LOGGED_OUT
    transport.responses["qobuz"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "qobuz://406889200.flac",
                      "name": "Comfortably Numb", "artist": "Pink Floyd"}]},
    )
    return transport


# -- the swap ----------------------------------------------------------------
def test_a_logged_out_default_service_hands_the_request_to_a_connected_one(
        router, qobuz_has_the_song):
    # The phrase that started this: TIDAL is the default and cannot answer,
    # Qobuz can, and the reply says which one did.
    reply = router.handle("metti Comfortably Numb dei Pink Floyd")
    assert str(reply) == "Riproduco Comfortably Numb di Pink Floyd da Qobuz."
    assert ["playlist", "play", "qobuz://406889200.flac"] in \
        qobuz_has_the_song.commands()


def test_the_swap_survives_the_artist_being_named(router, qobuz_has_the_song):
    # «dei Pink Floyd» splits into title + artist and searches on both; the
    # connector is not what was broken, and must not start being.
    assert str(router.handle("metti Comfortably Numb")) == \
        "Riproduco Comfortably Numb di Pink Floyd da Qobuz."


def test_a_connected_default_service_is_not_swapped(router, transport, make_feed):
    transport.responses["tidal"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    transport.responses["qobuz"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    assert str(router.handle("metti Time")) == "Riproduco Time da TIDAL."
    assert not any(cmd[0] == "qobuz" for cmd in transport.commands())


def test_a_connected_service_with_nothing_to_offer_still_says_so(
        router, transport, make_feed):
    # The swap is about being ASKED, not about being answered. Both services
    # are up and neither has the song: that is a real miss and keeps its words.
    for tag in ("tidal", "qobuz"):
        transport.responses[tag] = make_feed(categories={"Songs": "S"},
                                             items={"S": []})
    assert str(router.handle("metti Zzzqqq")) == \
        "Non ho trovato nessun brano per Zzzqqq."


# -- when nobody can answer --------------------------------------------------
def test_no_connected_service_is_not_reported_as_a_missing_song(
        router, transport):
    for tag in ("tidal", "qobuz"):
        transport.responses[tag] = lambda cmd: LOGGED_OUT
    reply = router.handle("metti Comfortably Numb dei Pink Floyd")
    assert "Nessun servizio di streaming" in str(reply)
    assert "Non ho trovato" not in str(reply)
    assert reply.ok is False


def test_an_unreachable_server_is_not_a_disconnected_service(router, transport):
    # can_search() cannot answer at all here, and guessing "nothing is
    # connected" would send the user to the LMS settings to fix a hi-fi that
    # is simply switched off.
    transport.raise_on.add("tidal")
    transport.raise_on.add("qobuz")
    assert str(router.handle("metti Time")) == \
        "Non riesco a contattare l'impianto in questo momento. Riprova tra poco."


def test_a_named_service_that_is_logged_out_is_named_in_the_answer(
        router, transport):
    # Named outright, so nothing is substituted for it — the user asked about
    # Qobuz and gets an answer about Qobuz.
    transport.responses["qobuz"] = lambda cmd: LOGGED_OUT
    reply = router.handle("da qobuz metti Time")
    assert str(reply) == ("Qobuz non è collegato. Apri le impostazioni di LMS "
                          "e rifai l'accesso.")


def test_a_kid_safe_refusal_outranks_the_offline_message(lms, transport,
                                                         tmp_path, clock):
    # A gate is about what was asked for. Answering a child "no streaming
    # service is connected" answers a question nobody put — and hands them a
    # plumbing excuse in place of a no. So the request is run even against a
    # service that cannot answer, and only a plain miss gets re-worded.
    ks = KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)
    ks.enable("123456", "parent")
    ks.edit_terms("add", "Bad Song", "parent")
    for tag in ("tidal", "qobuz"):
        transport.responses[tag] = lambda cmd: LOGGED_OUT
    reply = Router(lms, kidsafe=ks, client_id="kid").handle("metti Bad Song")
    assert str(reply) == actions.msg("blocked")
    assert all(cmd[0] != "playlist" for cmd in transport.commands())


# -- the other word order ----------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "da qobuz metti Time",          # the service first, as before
    "metti Time da qobuz",          # ...and last, which is how it is spoken
    "metti Time su qobuz",
    "riproduci Time con qobuz",
    "metti Time da cobuz",          # what it-IT actually transcribes
])
def test_a_service_named_at_either_end_of_the_phrase(router, transport,
                                                     make_feed, phrase):
    # The suffix form is the one that was missing: «metti Time da Qobuz»
    # matched no service pattern at all, fell through to the source selector
    # and was answered by the default service — so naming Qobuz out loud, in
    # the order people actually say it, did nothing whatsoever.
    transport.responses["qobuz"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    assert str(router.handle(phrase, source="local")) == "Riproduco Time da Qobuz."
    assert ["playlist", "play", "qobuz://9.flac"] in transport.commands()


@pytest.mark.parametrize("lang,phrase", [
    ("en", "play Time on qobuz"),
    ("en", "put Time on qobuz"),
    ("fr", "mets Time sur qobuz"),
    ("de", "spiel Time auf qobuz"),
])
def test_the_suffix_form_in_every_language(lms, transport, make_feed, lang, phrase):
    transport.responses["qobuz"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    reply = Router(lms).handle(phrase, source="local", lang=lang)
    assert ["playlist", "play", "qobuz://9.flac"] in transport.commands(), reply
    assert "Qobuz" in str(reply)


def test_a_trailing_connector_is_still_an_artist_and_not_a_service(
        router, transport, make_feed):
    # The suffix form leaves «di»/«von»/«de» alone on purpose: those name an
    # artist. «metti Comfortably Numb dei Pink Floyd» must stay one request
    # about Pink Floyd, not a request routed at a service called "Pink Floyd".
    transport.responses["tidal"] = make_feed(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://2.flc",
                      "name": "Comfortably Numb", "artist": "Pink Floyd"}]},
    )
    assert str(router.handle("metti Comfortably Numb dei Pink Floyd")) == \
        "Riproduco Comfortably Numb di Pink Floyd da TIDAL."
