"""Library rows whose audio belongs to a plugin that is logged out.

Read off a live Daphile (LMS 9.0.3), 2026-08-29. «metti Teddy Swims» answered
«Riproduco Teddy Swims dalla tua musica» and nothing played: the ten tracks in
the library were TIDAL favourites the plugin had imported — library ids,
``artist_id``, ``album_id``, everything a local row has, and
``url: tidal://322955652.flc`` for audio. TIDAL had lost its tokens
(«Did find neither access nor refresh token»), so ``playlistcontrol`` loaded
ten tracks, LMS answered OK, the player walked the whole queue failing each one
and stopped at index 9. Qobuz was connected on the same server and had the
artist.

What the LMS says about such a row, verbatim from that server:

* ``albums  tags:E`` -> ``extid: "tidal:album:322955651"``
* ``artists tags:E`` -> ``extid: "qobuz:artist:6505891,tidal:artist:15694955"``
* ``titles  tags:u`` -> ``url: "tidal://322955655.flc"``

and a row read off a disk carries no ``extid`` at all. The artist line is why
the ``extid`` alone does not settle it: it names two services while every track
in the library came from one of them.
"""

import pytest

from conftest import FakeLicense
from pro.kidsafe import KidSafe
from router import Router
from test_service_fallback import LOGGED_OUT

ARTIST_ID = 1010
ALBUM_ID = 280
# The album as the library holds it: TIDAL urls, TIDAL extid, local ids.
IMPORTED_TRACKS = [
    {"id": 2899 + n, "title": f"Live Track {n + 1}", "artist": "Teddy Swims",
     "url": f"tidal://32295565{n}.flc"}
    for n in range(3)
]


@pytest.fixture
def router(lms):
    return Router(lms)


@pytest.fixture
def imported_library(transport):
    """A library whose only Teddy Swims rows were imported by TIDAL."""
    transport.responses["artists"] = {"artists_loop": [
        {"id": ARTIST_ID, "artist": "Teddy Swims",
         "extid": "qobuz:artist:6505891,tidal:artist:15694955"}]}
    transport.responses["albums"] = {"albums_loop": [
        {"id": ALBUM_ID, "album": "I've Tried Everything But Therapy",
         "artist": "Teddy Swims", "extid": "tidal:album:322955651"}]}
    transport.responses["titles"] = {"titles_loop": IMPORTED_TRACKS}
    return transport


@pytest.fixture
def qobuz_has_the_artist(imported_library, make_feed):
    """TIDAL logged out, Qobuz connected and holding the artist."""
    imported_library.responses["tidal"] = lambda cmd: LOGGED_OUT
    imported_library.responses["qobuz"] = make_feed(
        categories={"Artists": "A", "Songs": "S"},
        items={"A": [{"type": "outline", "id": "AR", "name": "Teddy Swims"}],
               "AR": [{"name": "Songs", "id": "TT"}],
               "TT": [{"isaudio": 1, "url": "qobuz://1.flac",
                       "name": "Lose Control"}],
               "S": [{"isaudio": 1, "url": "qobuz://2.flac",
                      "name": "Lose Control", "artist": "Teddy Swims"}]},
    )
    return imported_library


def _played(transport):
    return [cmd for cmd in transport.commands()
            if cmd[:2] in (["playlist", "play"], ["playlistcontrol", "cmd:load"])]


# -- the defect --------------------------------------------------------------
def test_a_request_naming_no_source_is_played_by_a_service_that_can(
        router, qobuz_has_the_artist):
    # The phrase that started this. The library's only copy is TIDAL's and
    # TIDAL is logged out, so the library declines and the request carries on
    # to a service that can actually play it — and the reply says which.
    reply = router.handle("metti canzoni di Teddy Swims", source="auto")
    assert str(reply) == "Riproduco la musica di Teddy Swims da Qobuz."
    assert ["playlist", "play", "qobuz://1.flac"] in \
        qobuz_has_the_artist.commands()


def test_the_silent_queue_is_never_loaded(router, qobuz_has_the_artist):
    # The whole bug in one assertion: playlistcontrol on the imported artist
    # is what LMS accepted and the room did not hear.
    router.handle("metti canzoni di Teddy Swims", source="auto")
    assert not any(cmd[0] == "playlistcontrol"
                   for cmd in qobuz_has_the_artist.commands())


def test_a_generic_request_is_not_answered_by_the_imported_rows(
        router, qobuz_has_the_artist):
    # Same for the generic branch, which scores albums, artists and tracks
    # against each other: all three categories are TIDAL's here.
    assert str(router.handle("metti Teddy Swims", source="auto")) == \
        "Riproduco Lose Control di Teddy Swims da Qobuz."


# -- a plugin that is logged IN is not touched -------------------------------
def test_imported_rows_play_from_the_library_while_the_plugin_is_connected(
        router, imported_library, make_feed):
    imported_library.responses["tidal"] = make_feed()
    assert str(router.handle("metti canzoni di Teddy Swims",
                             source="auto")) == \
        "Riproduco Teddy Swims dalla tua musica."
    assert ["playlistcontrol", "cmd:load", f"artist_id:{ARTIST_ID}"] in \
        imported_library.commands()


def test_a_library_of_files_asks_nobody_anything(router, transport, make_feed):
    # No extid, no url: a row read off a disk costs not one extra query, which
    # is nearly every row in nearly every library.
    transport.responses["artists"] = {"artists_loop": [
        {"id": 7, "artist": "Teddy Swims"}]}
    transport.responses["albums"] = {"albums_loop": []}
    transport.responses["titles"] = {"titles_loop": []}
    transport.responses["tidal"] = make_feed()
    router.handle("metti canzoni di Teddy Swims", source="auto")
    # `titles` is asked for the search itself, never for a playability probe:
    # the artist branch reads artists alone.
    assert not any(cmd[0] == "titles" for cmd in transport.commands())


# -- «dalla mia musica …»: the truth, and a way out --------------------------
def test_naming_the_library_gets_the_reason_and_an_offer(
        router, qobuz_has_the_artist):
    reply = router.handle("dalla mia musica metti canzoni di Teddy Swims")
    assert str(reply) == (
        "Quello che ho di Teddy Swims nella tua musica arriva da TIDAL, che "
        "non è collegato. Vuoi che la metta da Qobuz?")
    assert reply.ok is False
    assert not _played(qobuz_has_the_artist)


def test_yes_plays_it_from_the_offered_service(router, qobuz_has_the_artist):
    router.handle("dalla mia musica metti canzoni di Teddy Swims")
    assert str(router.handle("sì")) == \
        "Riproduco la musica di Teddy Swims da Qobuz."
    assert ["playlist", "play", "qobuz://1.flac"] in \
        qobuz_has_the_artist.commands()


def test_no_closes_the_question_and_plays_nothing(router, qobuz_has_the_artist):
    router.handle("dalla mia musica metti canzoni di Teddy Swims")
    reply = router.handle("no")
    assert str(reply) == "Va bene."
    assert reply.ok is True
    assert not _played(qobuz_has_the_artist)
    # And the question is spent: a later «sì» is a phrase, not an answer.
    assert str(router.handle("sì")) != \
        "Riproduco la musica di Teddy Swims da Qobuz."


def test_with_nothing_else_connected_there_is_no_offer(
        router, imported_library):
    # Both services logged out: the reason is still owed, the offer is not.
    for tag in ("tidal", "qobuz"):
        imported_library.responses[tag] = lambda cmd: LOGGED_OUT
    reply = router.handle("dalla mia musica metti canzoni di Teddy Swims")
    assert str(reply) == (
        "Quello che ho di Teddy Swims nella tua musica arriva da TIDAL, che "
        "non è collegato.")
    assert router.offer is None


def test_the_local_source_selector_asks_the_same_question(
        lms, qobuz_has_the_artist):
    # «dalla mia musica» said with the UI selector instead of out loud. Same
    # request, same answer.
    router = Router(lms)
    reply = router.handle("metti canzoni di Teddy Swims", source="local")
    assert "Vuoi che la metta da Qobuz?" in str(reply)


# -- the offer itself --------------------------------------------------------
def test_a_named_service_that_is_logged_out_offers_a_connected_one(
        router, qobuz_has_the_artist):
    assert str(router.handle("da tidal metti canzoni di Teddy Swims")) == \
        "TIDAL non è collegato. Vuoi che la metta da Qobuz?"
    assert str(router.handle("va bene")) == \
        "Riproduco la musica di Teddy Swims da Qobuz."


def test_an_offer_expires(lms, qobuz_has_the_artist, clock):
    from conversation import OFFER_TTL

    router = Router(lms, now=clock)
    router.handle("da tidal metti canzoni di Teddy Swims")
    clock.t += OFFER_TTL + 1
    # Past the window «sì» is just a word again, and the router says so rather
    # than starting music nobody has asked for in five minutes.
    assert str(router.handle("sì")) != \
        "Riproduco la musica di Teddy Swims da Qobuz."
    assert not _played(qobuz_has_the_artist)


def test_a_turn_that_acted_on_something_else_closes_the_offer(
        router, qobuz_has_the_artist):
    router.handle("da tidal metti canzoni di Teddy Swims")
    router.handle("pausa")
    assert router.offer is None
    assert str(router.handle("sì")) != \
        "Riproduco la musica di Teddy Swims da Qobuz."


def test_a_turn_that_missed_leaves_the_offer_open(router, qobuz_has_the_artist):
    # handle_many replays a spoken turn once per recognition alternative, and
    # a badly transcribed one must not spend the question before the good one
    # arrives. Same asymmetry the mood has.
    router.handle("da tidal metti canzoni di Teddy Swims")
    router.handle("qwertyuiop asdfghjkl")
    assert str(router.handle("sì")) == \
        "Riproduco la musica di Teddy Swims da Qobuz."


def test_an_offer_ends_the_turn_for_handle_many(router, qobuz_has_the_artist):
    # Without a kind to stop on, the second alternative would be routed over
    # the question and the offer would be gone before it was read out.
    out = router.handle_many(["da tidal metti canzoni di Teddy Swims",
                              "metti canzoni di Teddy Swims"])
    assert out["speech"] == "TIDAL non è collegato. Vuoi che la metta da Qobuz?"
    assert out["needs_choice"] is True
    assert [c["say"] for c in out["choices"]] == ["Sì", "No"]


def test_a_kid_safe_refusal_still_outranks_the_offer(
        lms, qobuz_has_the_artist, tmp_path, clock):
    # A gate speaks for itself: a child asking for a blocked song must not be
    # handed a question about which streaming service to use instead.
    ks = KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)
    ks.enable("123456", "parent")
    ks.edit_terms("add", "Teddy Swims", "parent")
    router = Router(lms, kidsafe=ks, client_id="kid")
    reply = router.handle("da tidal metti canzoni di Teddy Swims")
    assert "Vuoi che" not in str(reply)
    assert router.offer is None


# -- the other three languages -----------------------------------------------
#
# Everything above is Italian, and everything above is one sentence built out
# of four language-pack entries (``local_prefix``, ``artist``, ``yes``, ``no``)
# and four catalog keys. A pack that ships three of them and forgets the fourth
# loses the whole conversation in that language and nothing else fails, so each
# one is asked the same three questions here, verbatim as the live server
# answered them.
LANGUAGES = [
    ("en",
     "from my music play songs by Teddy Swims",
     "from tidal play songs by Teddy Swims",
     "yes", "no",
     "What I have of Teddy Swims in your music comes from TIDAL, which isn't "
     "connected. Shall I play it from Qobuz?",
     "TIDAL isn't connected. Shall I play it from Qobuz?",
     "Playing music by Teddy Swims from Qobuz.",
     "All right."),
    ("fr",
     "dans ma musique mets la musique de Teddy Swims",
     "sur tidal mets la musique de Teddy Swims",
     "oui", "non",
     "Ce que j'ai de Teddy Swims dans ta musique vient de TIDAL, qui n'est "
     "pas connecté. Tu veux que je le mette depuis Qobuz ?",
     "TIDAL n'est pas connecté. Tu veux que je le mette depuis Qobuz ?",
     "Je mets la musique de Teddy Swims sur Qobuz.",
     "D'accord."),
    ("de",
     "aus meiner Musik spiel die Musik von Teddy Swims",
     "von tidal spiel die Musik von Teddy Swims",
     "ja", "nein",
     "Was ich von Teddy Swims in deiner Musik habe, kommt von TIDAL, und der "
     "ist nicht verbunden. Soll ich es von Qobuz abspielen?",
     "TIDAL ist nicht verbunden. Soll ich es von Qobuz abspielen?",
     "Ich spiele Musik von Teddy Swims von Qobuz.",
     "In Ordnung."),
]


@pytest.mark.parametrize(
    "lang,local_phrase,service_phrase,yes,no,local_q,service_q,playing,declined",
    LANGUAGES, ids=[row[0] for row in LANGUAGES])
def test_the_offer_works_in_every_language(
        router, qobuz_has_the_artist, lang, local_phrase, service_phrase,
        yes, no, local_q, service_q, playing, declined):
    # Naming the library: the reason, then the question, then the music.
    assert str(router.handle(local_phrase, lang=lang)) == local_q
    assert str(router.handle(yes, lang=lang)) == playing
    assert ["playlist", "play", "qobuz://1.flac"] in \
        qobuz_has_the_artist.commands()

    # Naming the service: the same question, and a «no» that closes it.
    assert str(router.handle(service_phrase, lang=lang)) == service_q
    assert str(router.handle(no, lang=lang)) == declined
    assert router.offer is None


@pytest.mark.parametrize("lang,phrase", [
    ("en", "play songs by Teddy Swims"),
    ("fr", "mets la musique de Teddy Swims"),
    ("de", "spiel die Musik von Teddy Swims"),
], ids=["en", "fr", "de"])
def test_no_source_named_reaches_a_connected_service_in_every_language(
        router, qobuz_has_the_artist, lang, phrase):
    # The selector's own default: the library declines because its only copy
    # is TIDAL's, and the request carries on rather than going quiet. No
    # question here — nobody named a source, so there is no preference to
    # override and nothing to ask about.
    playing = dict((row[0], row[7]) for row in LANGUAGES)[lang]
    assert str(router.handle(phrase, source="auto", lang=lang)) == playing
    assert router.offer is None
