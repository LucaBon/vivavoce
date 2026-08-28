"""German support: DE router patterns, DE replies, DE parsing separators.

Mirrors ``tests/test_english.py`` with lang="de", plus the battery German
needs and the other two do not: the separable verb («leg X auf», «mach die
Musik an»), the adjective that changes sides of the marker noun («etwas
Entspannendes» / «etwas entspannende Musik»), and the words that look like
transport commands until you notice they are half of something else — «mach
lauter» against «mach die Musik an», «aus» in a title against «mach aus».
"""

import pytest

import actions
import messages
from messages import msg, set_lang
from router import Router


@pytest.fixture
def router(lms):
    return Router(lms)


# -- catalog ----------------------------------------------------------------
def test_catalog_matches_the_italian_one():
    assert set(messages.IT) == set(messages.DE)


def test_msg_lang_selection():
    assert msg("paused", lang="de") == "Pausiert."
    assert msg("paused", lang="it") == "In pausa."
    set_lang("de")
    assert msg("paused") == "Pausiert."
    set_lang("it")
    assert msg("paused") == "In pausa."


# -- parsing (actions) --------------------------------------------------------
def test_parse_song_query_german_von_and_album():
    q = actions.parse_song_query("Comfortably Numb von Pink Floyd")
    assert q == {"title": "Comfortably Numb", "artist": "Pink Floyd", "album": None}
    q = actions.parse_song_query("Time aus dem Album The Dark Side of the Moon")
    assert q["title"] == "Time"
    assert q["album"] == "The Dark Side of the Moon"


def test_von_a_pronoun_is_not_an_artist():
    # «Ein Teil von mir» is a title; there is no singer called "mir". Without
    # the guard the split searches for one and drags every score down.
    q = actions.parse_song_query("Ein Teil von mir")
    assert q["artist"] is None
    assert q["title"] == "Ein Teil von mir"


def test_german_lead_filler_is_stripped():
    assert actions.parse_song_query("das Lied Time")["title"] == "Time"


# -- transport & info ---------------------------------------------------------
@pytest.mark.parametrize(
    "phrase, expected_cmd",
    [
        ("pause", ["pause", "1"]),
        ("stopp", ["pause", "1"]),
        ("mach die Musik aus", ["pause", "1"]),
        ("weiter", ["pause", "0"]),
        ("spiel weiter", ["pause", "0"]),
        ("nächster Titel", ["playlist", "index", "+1"]),
        ("überspring das", ["playlist", "index", "+1"]),
        ("vorheriger Titel", ["playlist", "index", "-1"]),
        ("zurück", ["playlist", "index", "-1"]),
        ("mach die Lautstärke lauter", ["mixer", "volume", "+5"]),
        ("lauter", ["mixer", "volume", "+5"]),
        ("mach die Lautstärke leiser", ["mixer", "volume", "-5"]),
        ("leiser", ["mixer", "volume", "-5"]),
    ],
)
def test_transport_phrases_de(router, transport, phrase, expected_cmd):
    router.handle(phrase, lang="de")
    assert transport.last_call()[1] == expected_cmd


def test_transport_replies_are_german(router, transport):
    assert router.handle("pause", lang="de") == "Pausiert."
    assert router.handle("weiter", lang="de") == "Ich spiele weiter."


def test_now_playing_de(router, transport):
    transport.responses["status"] = {"playlist_loop": [{"title": "Time", "artist": "PF"}]}
    assert router.handle("was läuft gerade", lang="de") == "Gerade läuft Time von PF."


@pytest.mark.parametrize(
    "phrase",
    ["was läuft gerade",
     "was spielt gerade",
     "welches Lied läuft",
     "wer singt das",
     "wer ist das",
     "was ist das für ein Lied"],
)
def test_now_playing_variants_de(router, transport, phrase):
    transport.responses["status"] = {"playlist_loop": [{"title": "Time", "artist": "PF"}]}
    assert router.handle(phrase, lang="de") == "Gerade läuft Time von PF."


# -- the sleep timer, said from both sides ------------------------------------
@pytest.mark.parametrize(
    "phrase, minutes",
    [("schalt in 30 Minuten aus", "30"),
     ("in 30 Minuten ausschalten", "30"),          # the particle leads instead
     ("stopp in einer halben Stunde", "30"),
     ("schalt in einer Stunde aus", "60"),
     ("schalt in zwei Stunden aus", "120"),
     ("schalt in dreißig Minuten aus", "30")],
)
def test_sleep_timer_de(router, transport, phrase, minutes):
    router.handle(phrase, lang="de")
    assert transport.last_call()[1] == ["sleep", str(int(minutes) * 60)]


def test_sleep_cancel_de(router, transport):
    router.handle("schalt in 30 Minuten aus", lang="de")
    assert router.handle("lösch den Schlaftimer", lang="de") == "Schlaftimer abgebrochen."


def test_a_title_carrying_in_is_not_a_timer(router, transport, make_tidal):
    # No sleep verb anywhere, so «in» is just a word in a title.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc",
                      "name": "Alone in the Dark"}]},
    )
    router.handle("spiel Alone in the Dark", source="tidal", lang="de")
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()
    assert not any(cmd[:1] == ["sleep"] for cmd in transport.commands())


# -- the separable verb -------------------------------------------------------
@pytest.mark.parametrize(
    "phrase",
    ["spiel Time",
     "starte Time",
     "hör Time",
     "leg Time auf",             # separable: the particle trails the title
     "ich möchte Time hören"],
)
def test_generic_play_variants_de(router, transport, make_tidal, phrase):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    router.handle(phrase, source="tidal", lang="de")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_a_title_ending_in_a_particle_keeps_it(router, transport, make_tidal):
    # «spiel Wach Auf» must search for "Wach Auf", not for "Wach": the plain
    # verbs never strip a particle, which is the whole reason ``generic_play``
    # does not list «leg»/«mach».
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://4.flc", "name": "Wach Auf"}]},
    )
    speech = router.handle("spiel Wach Auf", source="tidal", lang="de")
    assert speech.startswith("Ich spiele Wach Auf")
    assert ["playlist", "play", "tidal://4.flc"] in transport.commands()


def test_mach_lauter_is_volume_not_a_play(router, transport):
    # «mach» heads the play form («mach die Musik an»), the volume form and
    # the stop form alike: only the particle tells them apart.
    router.handle("mach lauter", lang="de")
    assert transport.last_call()[1] == ["mixer", "volume", "+5"]


def test_play_title_containing_transport_word_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://5.flc",
                      "name": "Stopp mich"}]},
    )
    router.handle("spiel Stopp mich von Queen", source="tidal", lang="de")
    assert ["playlist", "play", "tidal://5.flc"] in transport.commands()
    assert ["pause", "1"] not in transport.commands()


# -- playback + German replies ------------------------------------------------
def test_play_song_de_reply(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = router.handle("spiel Time", source="tidal", lang="de")
    assert speech.startswith("Ich spiele Time")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_play_song_not_found_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"}, items={"S": []})
    speech = router.handle("spiel Xyzzy", source="tidal", lang="de")
    assert speech == "Ich habe keinen Titel für Xyzzy gefunden."
    assert getattr(speech, "ok", None) is False


def test_play_album_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": "The Wall", "hasitems": 1}]},
    )
    speech = router.handle("spiel das Album The Wall", source="tidal", lang="de")
    assert speech == "Ich spiele das Album The Wall von TIDAL."


@pytest.mark.parametrize(
    "phrase",
    ["spiel Musik von Pink Floyd",
     "spiel etwas von Pink Floyd",
     "spiel alles von Pink Floyd",
     "spiel die Lieder von Pink Floyd",
     "spiel den Künstler Pink Floyd"],
)
def test_artist_variants_de(router, transport, make_tidal, phrase):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    router.handle(phrase, source="tidal", lang="de")
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


def test_qobuz_misheard_by_asr_de(router, transport, make_tidal):
    # de-DE Web Speech writes "qobuz" as «Kobutz»: the explicit-source phrase
    # must match the sound-alike, not just the exact spelling.
    transport.responses["qobuz"] = make_tidal(
        categories={"Tracks": "T"},
        items={"T": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    speech = router.handle("auf Kobutz spiel Time", source="local", lang="de")
    assert speech.startswith("Ich spiele Time")
    assert ["playlist", "play", "qobuz://9.flac"] in transport.commands()


def test_local_prefix_de(router, transport):
    transport.responses["search"] = {}
    speech = router.handle("aus meiner Musik spiel Xyzzy", lang="de")
    assert speech == "Ich habe Xyzzy in deiner Musik nicht gefunden."


def test_fallback_de(router, transport):
    speech = router.handle("wie wird das Wetter morgen", lang="de")
    assert speech.startswith("Das habe ich nicht verstanden.")


def test_handle_many_empty_de(router):
    out = router.handle_many([], lang="de")
    assert out["speech"] == "Ich habe nichts gehört."


# -- queue --------------------------------------------------------------------
def test_queue_add_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://3.flc", "name": "Money"}]},
    )
    speech = router.handle("füge Money zur Warteschlange hinzu",
                           source="tidal", lang="de")
    assert speech.startswith("Ich habe Money zur Warteschlange hinzugefügt")
    assert ["playlist", "add", "tidal://3.flc"] in transport.commands()


def test_queue_insert_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://3.flc", "name": "Money"}]},
    )
    speech = router.handle("spiel Money als nächstes", source="tidal", lang="de")
    assert speech.startswith("Ich spiele Money gleich nach diesem Titel")
    assert ["playlist", "insert", "tidal://3.flc"] in transport.commands()


def test_queue_clear_de(router, transport):
    assert router.handle("leere die Warteschlange", lang="de") == "Warteschlange geleert."


# -- numbered list flow ---------------------------------------------------------
def test_top_tracks_then_choose_number_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    speech = router.handle("welche Lieder von Pink Floyd", source="tidal", lang="de")
    assert speech.startswith("Hier sind die meistgehörten Titel von Pink Floyd.")
    assert "1: Time" in speech and "2: Money" in speech
    speech = router.handle("spiel Nummer zwei", source="tidal", lang="de")
    assert speech == "Ich spiele Money von TIDAL."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


def _open_list_de(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    router.handle("welche Lieder von Pink Floyd", source="tidal", lang="de")


@pytest.mark.parametrize("phrase", ["die zweite", "spiel das zweite Lied",
                                    "die zweiten", "zweite"])
def test_choose_ordinal_de(router, transport, make_tidal, phrase):
    _open_list_de(router, transport, make_tidal)
    assert router.handle(phrase, source="tidal", lang="de") == "Ich spiele Money von TIDAL."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


def test_choose_without_list_de(router, transport):
    assert router.handle("spiel Nummer zwei",
                         lang="de").startswith("Frag mich zuerst nach einer Liste")


# -- language isolation ----------------------------------------------------------
def test_italian_still_default(router, transport):
    assert router.handle("pausa") == "In pausa."


def test_languages_do_not_leak_between_requests(router, transport):
    assert router.handle("pause", lang="de") == "Pausiert."
    assert router.handle("pausa", lang="it") == "In pausa."
    assert router.handle("pause", lang="en") == "Paused."
