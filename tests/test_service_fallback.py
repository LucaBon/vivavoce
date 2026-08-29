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
    # Qobuz and gets an answer about Qobuz. Nothing else is connected either
    # (TIDAL answers no menu at all here), so there is nothing to offer: a
    # question whose only answer is "no" is not worth asking, and what is left
    # is the fix. The offer itself is in test_online_imports.py.
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


# -- naming a service says WHERE, never WHAT ---------------------------------
# The source-override branch used to hand every phrase to ``play_song``, so
# «da qobuz metti canzoni dei Pink Floyd» searched Qobuz for a *song* called
# "canzoni" — nothing matched the title, the artist check was skipped for want
# of a match to check, and the top row was played regardless: a Traxlab lullaby
# rendition of Wish You Were Here. Naming a service is a statement about where
# to look; the ladder that decides what to look FOR is the same one an unnamed
# request walks.
@pytest.fixture
def qobuz_knows_pink_floyd(transport, make_feed):
    transport.responses["qobuz"] = make_feed(
        categories={"Songs": "S", "Artists": "A", "Playlists": "P",
                    "Releases": "R"},
        items={
            # What a song search for "canzoni pink floyd" really came back
            # with, first row first.
            "S": [{"isaudio": 1, "url": "qobuz://1.flac",
                   "name": "Wish You Were Here", "artist": "Traxlab"}],
            "A": [{"type": "outline", "id": "AR", "name": "Pink Floyd"}],
            "AR": [{"name": "Songs", "id": "TT"}],
            "TT": [{"isaudio": 1, "url": "qobuz://10.flac", "name": "Time"},
                   {"isaudio": 1, "url": "qobuz://11.flac", "name": "Money"}],
            "R": [{"id": "AL", "name": "The Wall"}],
            "P": [{"id": "PL", "name": "Chill"}],
        },
    )
    return transport


def test_a_named_service_still_reaches_the_artist_branch(
        router, qobuz_knows_pink_floyd):
    reply = router.handle("da qobuz metti canzoni dei Pink Floyd")
    assert str(reply) == "Riproduco la musica di Pink Floyd da Qobuz."
    cmds = qobuz_knows_pink_floyd.commands()
    assert ["playlist", "play", "qobuz://10.flac"] in cmds
    assert ["playlist", "add", "qobuz://11.flac"] in cmds
    # The lullaby is still the first row of the Songs category; nothing asked.
    assert ["playlist", "play", "qobuz://1.flac"] not in cmds
    assert not any(p.startswith("search:canzoni") for c in cmds for p in c)


def test_a_named_service_still_reaches_the_album_branch(
        router, qobuz_knows_pink_floyd):
    assert str(router.handle("da qobuz metti l'album The Wall")) == \
        "Riproduco l'album The Wall da Qobuz."
    assert ["qobuz", "playlist", "play", "item_id:AL"] in \
        qobuz_knows_pink_floyd.commands()


def test_a_named_service_still_reaches_the_playlist_branch(
        router, qobuz_knows_pink_floyd):
    assert str(router.handle("da qobuz metti la playlist Chill")) == \
        "Riproduco la playlist Chill da Qobuz."
    assert ["qobuz", "playlist", "play", "item_id:PL"] in \
        qobuz_knows_pink_floyd.commands()


def test_the_suffix_word_order_reaches_the_album_branch_too(
        router, qobuz_knows_pink_floyd):
    # The verb now lives inside the capture, which is what lets the album
    # pattern — anchored on that verb — read the re-routed phrase.
    assert str(router.handle("metti l'album The Wall da qobuz")) == \
        "Riproduco l'album The Wall da Qobuz."
    assert ["qobuz", "playlist", "play", "item_id:AL"] in \
        qobuz_knows_pink_floyd.commands()


def test_a_play_verb_the_prefix_form_did_not_know_is_not_part_of_the_title(
        router, qobuz_knows_pink_floyd):
    # «suona» was in the suffix form's verb list and not the prefix form's, so
    # the prefix form searched for a song called "suona pink floyd".
    router.handle("da qobuz suona Pink Floyd")
    searches = [p for c in qobuz_knows_pink_floyd.commands() for p in c
                if p.startswith("search:")]
    assert searches and all(s == "search:Pink Floyd" for s in searches)


def test_a_named_service_with_no_verb_at_all_is_still_a_song_request(
        router, qobuz_knows_pink_floyd):
    # «da qobuz pink floyd» names no branch: it stays the generic song search
    # it has always been.
    assert str(router.handle("da qobuz Wish You Were Here")) == \
        "Riproduco Wish You Were Here di Traxlab da Qobuz."


def test_a_named_but_logged_out_service_is_not_swapped_on_the_artist_branch(
        router, transport, make_feed):
    # The regression guard for _resolve_named: a NAMED service is answered
    # about, never silently replaced — including now that the branch is not
    # play_song any more. TIDAL is connected here and holds the artist, so it
    # is offered by name; what must not happen is that it starts playing
    # because the question was never put.
    transport.responses["qobuz"] = lambda cmd: LOGGED_OUT
    transport.responses["tidal"] = make_feed(
        categories={"Artists": "A"},
        items={"A": [{"type": "outline", "id": "AR", "name": "Pink Floyd"}],
               "AR": [{"name": "Top Tracks", "id": "TT"}],
               "TT": [{"isaudio": 1, "url": "tidal://5.flc", "name": "Time"}]},
    )
    assert str(router.handle("da qobuz metti canzoni dei Pink Floyd")) == \
        "Qobuz non è collegato. Vuoi che la metta da TIDAL?"
    assert ["playlist", "play", "tidal://5.flc"] not in transport.commands()


@pytest.mark.parametrize("lang,phrase,artist", [
    ("it", "da qobuz metti canzoni dei Pink Floyd", "Pink Floyd"),
    ("it", "metti le canzoni dei Pink Floyd da qobuz", "Pink Floyd"),
    ("en", "from qobuz play songs by Pink Floyd", "Pink Floyd"),
    ("en", "play the music by Pink Floyd on qobuz", "Pink Floyd"),
    ("de", "von qobuz spiel die Musik von Pink Floyd", "Pink Floyd"),
    ("de", "spiel die Musik von Pink Floyd auf qobuz", "Pink Floyd"),
    ("fr", "sur qobuz mets la musique de Pink Floyd", "Pink Floyd"),
])
# Not covered, and not by this change: «spiel … auf qobuz ab», with the German
# separable particle AFTER the service name. The prefix template matches
# «auf qobuz ab» mid-sentence and reads "ab" as the whole request — it did
# before this branch was rewritten and it still does. Closing it means
# teaching both service templates about a trailing particle, which is a
# question about German word order rather than about which branch answers.
def test_the_artist_branch_survives_the_service_phrase_in_every_language(
        lms, qobuz_knows_pink_floyd, lang, phrase, artist):
    reply = Router(lms).handle(phrase, source="local", lang=lang)
    assert ["playlist", "play", "qobuz://10.flac"] in \
        qobuz_knows_pink_floyd.commands(), reply
    assert artist in str(reply)
