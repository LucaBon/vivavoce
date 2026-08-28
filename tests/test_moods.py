"""Vague requests (T2.4, strada A) — engine/moods.py and its routing.

Two things are being defended here, and the second matters more than the first.

The first is that a mood plays something: local genre before curated playlist,
read back out loud, changeable with «un'altra».

The second is that **nothing else changed**. A mood pattern sits ahead of every
play verb in the router, which is only safe because of a double filter — the
marker noun, then the whole-tail lookup. The negative tests below are that
filter's proof, and they are meant to be checked by mutation: break either half
in moods.py or in a language pack, and they have to go red. If they still pass,
they are testing nothing.
"""

import os

import pytest

import moods
from lang import PACKS
from router import Router

GENRES = [
    {"id": 1, "genre": "Rock"},
    {"id": 2, "genre": "Ambient"},
    {"id": 3, "genre": "Classic Rock"},
    {"id": 4, "genre": "Jazz"},
    {"id": 5, "genre": "Rockabilly"},
]


@pytest.fixture
def library(transport):
    """A local library with genres LMS would report."""
    transport.responses["genres"] = {"genres_loop": list(GENRES)}
    return transport


@pytest.fixture
def router(lms):
    return Router(lms)


YEARS = [{"year": 1967}, {"year": 1978}, {"year": 1985}, {"year": 1987},
         {"year": 1994}]


@pytest.fixture
def decades(library):
    """The same library, plus the years LMS would report for it."""
    library.responses["years"] = {"years_loop": list(YEARS)}
    return library


def _loaded(transport, prefix):
    """The value the router loaded under ``prefix:``, or None."""
    for cmd in transport.commands():
        if cmd[:2] == ["playlistcontrol", "cmd:load"]:
            for part in cmd[2:]:
                if part.startswith(prefix):
                    return part[len(prefix):]
    return None


def played_genre(transport):
    """The genre_id the router loaded, or None."""
    return _loaded(transport, "genre_id:")


def played_year(transport):
    """The year the router loaded, or None."""
    return _loaded(transport, "year:")


def loads(transport):
    """Every playlistcontrol cmd:load the router issued."""
    return [cmd for cmd in transport.commands()
            if cmd[:2] == ["playlistcontrol", "cmd:load"]]


# -- the table itself ---------------------------------------------------------

def test_every_mood_offers_a_library_axis_and_a_playlist():
    # A mood with only one of the two has only one of the two fallbacks, and
    # would fail silently for exactly the listeners who don't have the other.
    for key, mood in moods.MOODS.items():
        assert mood.get("genres") or mood.get("years"), f"{key} has no axis"
        assert mood["playlists"], f"{key} has no playlist queries"


def test_a_mood_resolves_on_exactly_one_axis():
    # play_mood branches on which key is present. An entry carrying both would
    # silently lose one of them, and an entry carrying neither would crash.
    for key, mood in moods.MOODS.items():
        assert ("genres" in mood) != ("years" in mood), (
            f"{key} must have genres or years, not both and not neither")


def test_a_decade_is_an_interval_not_a_range_filter():
    # No LMS filter accepts a range, so the interval is ours to walk: it has to
    # be a well-formed (start, end) or _pick_year silently matches nothing.
    for key, mood in moods.MOODS.items():
        if "years" not in mood:
            continue
        start, end = mood["years"]
        assert 1900 < start < end < 2100, key


# The second pass (T2.4-bis): the metadata axes LMS already carries. These are
# the phrases the corpus had and the vocabulary did not - asserted through the
# real double filter (pattern, then whole-tail lookup), not by reading the
# table, so a phrase the pattern cannot reach still fails here.
NEW_PHRASES_IT = [
    ("metti musica natalizia", "christmas"),
    ("metti qualcosa di natalizio", "christmas"),
    ("metti musica per natale", "christmas"),
    ("metti qualcosa di strumentale", "instrumental"),
    ("metti qualcosa senza parole", "instrumental"),
    ("metti qualcosa di estivo", "summer"),
    ("metti musica da spiaggia", "summer"),
    ("metti musica anni ottanta", "eighties"),
    ("metti musica anni 80", "eighties"),
    ("metti qualcosa degli anni sessanta", "sixties"),
    ("metti qualcosa dagli anni novanta", "nineties"),
    ("metti musica anni settanta", "seventies"),
]

NEW_PHRASES_EN = [
    ("put on some christmas music", "christmas"),
    ("play something for christmas", "christmas"),
    ("play something instrumental", "instrumental"),
    ("play something without words", "instrumental"),
    ("play something with no words", "instrumental"),
    ("play something summery", "summer"),
    ("play some eighties music", "eighties"),
    ("play something from the eighties", "eighties"),
    ("play some 80s music", "eighties"),
    ("play something from the sixties", "sixties"),
    ("play some nineties music", "nineties"),
    ("play some seventies music", "seventies"),
]

# German, where the mood may sit on either side of the marker noun: «etwas
# Entspannendes» puts it after, «etwas entspannende Musik» before. Both shapes
# are here on purpose - the pattern has to reach the tail through a trailing
# «Musik»/«Lieder», and the separable verb has to find its own particle
# («mach ... an») without it landing in the lookup.
NEW_PHRASES_DE = [
    ("spiel etwas Entspannendes", "relax"),
    ("spiel etwas entspannende Musik", "relax"),
    ("mach Musik für die Party an", "party"),
    ("spiel Musik zum Einschlafen", "sleep"),
    ("spiel etwas Fröhliches", "happy"),
    ("spiel Musik zum Lernen", "focus"),
    ("spiel etwas weihnachtliche Musik", "christmas"),
    ("spiel Musik zu Weihnachten", "christmas"),
    ("spiel etwas Instrumentales", "instrumental"),
    ("spiel etwas ohne Gesang", "instrumental"),
    ("spiel etwas Sommerliches", "summer"),
    ("spiel Musik aus den Achtzigern", "eighties"),
    ("spiel etwas aus den 80ern", "eighties"),
    ("spiel Musik aus den Sechzigern", "sixties"),
    ("spiel etwas Klassisches", "classical"),
]


def resolved(phrase, code):
    """The mood key a spoken phrase really produces - both filters, in the
    order the router runs them."""
    pack = PACKS[code]
    m = pack.PATTERNS["mood"].search(phrase)
    if not m:
        return None
    return moods.match_mood(m.group(1).strip(), pack.MOOD_WORDS)


@pytest.mark.parametrize("phrase,key", NEW_PHRASES_IT)
def test_the_new_italian_phrases_reach_their_mood(phrase, key):
    assert resolved(phrase, "it") == key


@pytest.mark.parametrize("phrase,key", NEW_PHRASES_EN)
def test_the_new_english_phrases_reach_their_mood(phrase, key):
    assert resolved(phrase, "en") == key


@pytest.mark.parametrize("phrase,key", NEW_PHRASES_DE)
def test_the_new_german_phrases_reach_their_mood(phrase, key):
    assert resolved(phrase, "de") == key


@pytest.mark.parametrize(
    "phrase",
    # The anchor and the marker noun, in German. Each of these carries a mood
    # word and asks for something else entirely; a pattern without ^ or
    # without the marker starts the music on all four.
    ["mach die Musik aus",
     "stopp die entspannende Musik",
     "ich will keine traurige Musik",
     "blockiere traurige Musik"],
)
def test_a_german_phrase_that_is_not_a_request_to_play(phrase):
    assert resolved(phrase, "de") is None


@pytest.mark.parametrize("code", sorted(PACKS))
def test_every_spoken_phrase_points_at_a_real_mood(code):
    for phrase, key in PACKS[code].MOOD_WORDS.items():
        assert key in moods.MOODS, f"{code}: {phrase!r} -> unknown mood {key!r}"


@pytest.mark.parametrize("code", sorted(PACKS))
def test_spoken_phrases_are_written_normalized(code):
    # The lookup is a dict hit on the normalized tail, so an entry spelled with
    # an accent or an apostrophe would simply never match — silently, which is
    # the worst way for a vocabulary entry to be wrong.
    from actions import _normalize
    for phrase in PACKS[code].MOOD_WORDS:
        assert _normalize(phrase) == phrase, f"{code}: {phrase!r} is not normalized"


# -- resolution order: the library first --------------------------------------

def test_a_mood_plays_a_local_genre(router, library):
    reply = router.handle("metti qualcosa di rilassante")
    assert str(reply) == "Ho messo un po' di Ambient. Se non va, dimmi un'altra."
    assert played_genre(library) == "2"


def test_a_mood_does_not_touch_the_players_shuffle_setting(router, library):
    # `playlist shuffle 1` is the player's shuffle *preference*, not "shuffle
    # this queue": one mood would leave every later album playing out of
    # order, with no voice command anywhere to turn it back off. The repeated
    # opening track is the lesser of the two, and this is the test that keeps
    # someone from "fixing" it the easy way.
    router.handle("metti qualcosa di rilassante")
    assert not any(cmd[:2] == ["playlist", "shuffle"] for cmd in library.commands())


def test_the_library_wins_over_the_service(router, library, make_tidal):
    # 'relax' lists Ambient among its genres and "Relaxing" among its
    # playlists; the library has Ambient, so the service is never asked.
    library.responses["tidal"] = make_tidal(
        categories={"Playlists": "P"},
        items={"P": [{"id": "pl1", "name": "Relaxing Classical"}]},
    )
    reply = router.handle("metti qualcosa di rilassante", source="tidal")
    assert "Ambient" in str(reply)
    assert not any(cmd[0] == "tidal" for cmd in library.commands())


def test_the_service_answers_when_the_library_cannot(router, library, make_tidal):
    library.responses["genres"] = {"genres_loop": [{"id": 9, "genre": "Polka"}]}
    library.responses["tidal"] = make_tidal(
        categories={"Playlists": "P"},
        items={"P": [{"id": "pl1", "name": "Relaxing Classical"}]},
    )
    reply = router.handle("metti qualcosa di rilassante", source="tidal")
    assert str(reply) == (
        "Ho messo la playlist Relaxing Classical. Se non va, dimmi un'altra.")
    assert ["tidal", "playlist", "play", "item_id:pl1"] in library.commands()


def test_a_local_request_never_falls_back_to_the_service(router, library, make_tidal):
    # Asking for your own library and being handed a streaming playlist is not
    # a fallback, it's a different answer to a different question.
    library.responses["genres"] = {"genres_loop": [{"id": 9, "genre": "Polka"}]}
    library.responses["tidal"] = make_tidal(
        categories={"Playlists": "P"},
        items={"P": [{"id": "pl1", "name": "Relaxing Classical"}]},
    )
    reply = router.handle("metti qualcosa di rilassante", source="local")
    assert not reply.ok
    assert not any(cmd[0] == "tidal" for cmd in library.commands())


def test_a_genre_tag_matches_as_a_whole_word_only(router, library):
    # "Classic Rock" answers `rock`; "Rockabilly" must not.
    library.responses["genres"] = {"genres_loop": [
        {"id": 5, "genre": "Rockabilly"}, {"id": 3, "genre": "Classic Rock"}]}
    router.handle("metti un po' di rock")
    assert played_genre(library) == "3"


# -- «un'altra» ---------------------------------------------------------------

def test_a_genre_load_asks_for_a_random_album_order(router, library):
    # The third way out of "the same mood opens on the same track every
    # evening", after `playlist shuffle 1` was refused for being the player's
    # standing preference: `sort:random` is scoped to this one call. It is not
    # decoration and it is not free to drop - without it the load is
    # deterministic again, silently.
    router.handle("metti qualcosa di rilassante")
    assert loads(library) == [["playlistcontrol", "cmd:load", "genre_id:2",
                               "sort:random"]]


# -- the year axis ------------------------------------------------------------

def test_a_decade_plays_one_year_of_it(router, decades):
    reply = router.handle("metti musica anni ottanta")
    assert str(reply) == "Ho messo qualcosa del 1985. Se non va, dimmi un'altra."
    assert played_year(decades) == "1985"


def test_a_year_is_not_handed_to_a_foreign_voice(router, decades):
    # `terms` is the list of foreign names in the reply, and the web client
    # gives each one to a foreign-language voice (static/js/tts.js). A year is
    # not a name: detectLang() finds nothing to go on in "1985" and falls
    # through to the foreign default, so the Italian sentence broke into three
    # utterances around an English voice reading nineteen eighty-five. The
    # re-roll still has to remember the year, which is what `label` is for.
    reply = router.handle("metti musica anni ottanta")
    assert reply.ok is True
    assert reply.terms == []
    assert reply.label == "1985"


def test_a_genre_is_still_named_for_the_voice(router, library):
    # The control: on the genre axis the choice IS a name, and it must keep
    # reaching the voice that can pronounce it.
    reply = router.handle("metti qualcosa di rilassante")
    assert reply.ok is True
    assert reply.terms == ["Ambient"] and reply.label == "Ambient"


def test_a_decade_load_is_a_single_year_and_a_random_order(router, decades):
    # `year:` never takes a range anywhere in the CLI, and loading the whole
    # decade would be cmd:load plus nine cmd:add - and would leave the re-roll
    # with nothing to exclude.
    router.handle("metti musica anni ottanta")
    assert loads(decades) == [["playlistcontrol", "cmd:load", "year:1985",
                               "sort:random"]]


def test_the_years_are_asked_for_the_way_lms_reports_them(router, decades):
    # `years` is not `genres`: it wants hasAlbums:1, and its loop is keyed by
    # `year`, not by `id`. Copying local_genres verbatim would return nothing.
    router.handle("metti musica anni ottanta")
    asked = [cmd for cmd in decades.commands() if cmd[0] == "years"]
    assert asked and "hasAlbums:1" in asked[0], asked


def test_another_one_gives_another_year_of_the_same_decade(router, decades):
    first = router.handle("metti musica anni ottanta")
    second = router.handle("un'altra")
    assert "1985" in str(first)
    assert "1987" in str(second)
    assert second.ok


def test_a_decade_the_library_has_nothing_from_does_not_pretend(router, decades):
    # A library that stops in 1979: answering «anni ottanta» with 1978 because
    # it is the closest would be exactly the silent wrong answer this module
    # exists to avoid, and it is what a missing bounds check would do.
    decades.responses["years"] = {"years_loop": [{"year": 1967}, {"year": 1978}]}
    reply = router.handle("metti musica anni ottanta", source="local")
    assert not reply.ok
    assert not loads(decades)


def test_a_year_outside_the_decade_is_never_picked(router, decades):
    router.handle("metti musica anni sessanta", source="local")
    assert played_year(decades) == "1967"


def test_a_decade_falls_back_to_the_service_like_any_other_mood(router, decades,
                                                                make_tidal):
    decades.responses["years"] = {"years_loop": [{"year": 1967}]}
    decades.responses["tidal"] = make_tidal(
        categories={"Playlists": "P"},
        items={"P": [{"id": "pl1", "name": "80s Hits"}]},
    )
    reply = router.handle("metti musica anni ottanta", source="tidal")
    assert str(reply) == "Ho messo la playlist 80s Hits. Se non va, dimmi un'altra."


def test_an_unreachable_server_is_not_an_empty_decade(router, transport):
    transport.raise_on.add("years")
    reply = router.handle("metti musica anni ottanta")
    assert str(reply) == (
        "Non riesco a contattare l'impianto in questo momento. Riprova tra poco.")
    assert not reply.ok


def test_a_malformed_year_row_is_skipped_not_played(router, decades):
    # LMS has been known to report an empty year row for untagged material.
    # int("") would take the whole mood down with it.
    decades.responses["years"] = {"years_loop": [
        {"year": ""}, {"year": None}, {}, {"year": "1985"}]}
    reply = router.handle("metti musica anni ottanta")
    assert reply.ok, str(reply)
    assert played_year(decades) == "1985"


def test_a_decade_in_english(router, decades):
    reply = router.handle("play some eighties music", lang="en")
    assert str(reply) == (
        "I've put on something from 1985. Say another one if it doesn't fit.")


def test_another_one_picks_something_else(router, library):
    first = router.handle("metti qualcosa di energico")
    second = router.handle("un'altra")
    assert "Rock" in str(first)
    assert str(second) != str(first)
    assert second.ok


def test_another_one_says_so_when_the_ideas_run_out(router, library):
    library.responses["genres"] = {"genres_loop": [{"id": 2, "genre": "Ambient"}]}
    router.handle("metti qualcosa di rilassante")
    reply = router.handle("un'altra")
    assert str(reply) == "Ho finito le idee. Prova a dirmi un genere."
    assert not reply.ok


def test_an_exhausted_mood_does_not_answer_again(router, library):
    # Once it has said it is out of ideas the thread is over; a second
    # «un'altra» must not re-roll the same mood forever.
    library.responses["genres"] = {"genres_loop": [{"id": 2, "genre": "Ambient"}]}
    router.handle("metti qualcosa di rilassante")
    router.handle("un'altra")
    assert router.mood is None


def test_a_mood_expires(lms, library):
    clock = [1000.0]
    router = Router(lms, now=lambda: clock[0])
    router.handle("metti qualcosa di rilassante")
    clock[0] += 10_000
    reply = router.handle("un'altra")
    assert "Ambient" not in str(reply)
    assert router.mood is None


def test_another_command_ends_the_mood(router, library, make_tidal):
    library.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    router.handle("metti qualcosa di rilassante")
    router.handle("metti Time", source="tidal")
    reply = router.handle("un'altra")
    # Back to being an unrecognised phrase, not a re-roll of a mood the
    # conversation walked away from two turns ago.
    assert router._unmatched
    assert "Ambient" not in str(reply)


def test_a_phrase_nobody_understood_does_not_end_the_mood(router, library):
    # 'energetic' has two answers in this library (Rock, Classic Rock), so a
    # surviving mood really re-rolls instead of only reporting exhaustion.
    router.handle("metti qualcosa di energico")
    router.handle("asdfgh qwerty")           # goes nowhere
    reply = router.handle("un'altra")
    assert reply.ok, "a miss is not the conversation moving on"


def test_a_bad_recognition_alternative_does_not_end_the_mood(router, library):
    # handle_many replays one spoken turn once per recognition alternative and
    # promises that trying a miss has no side effect. Before the mood survived
    # misses, the badly-transcribed alternative killed it and the good one
    # then found nothing to re-roll — «un'altra» silently did nothing.
    router.handle("metti qualcosa di energico")
    out = router.handle_many(["un altro qwerty zzz che nessuno capisce", "un'altra"])
    assert out["ok"], out["speech"]
    assert out["used"] == "un'altra"


def test_playing_something_named_still_ends_the_mood(router, library, make_tidal):
    library.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    router.handle("metti qualcosa di rilassante")
    router.handle("metti Time", source="tidal")
    assert not router._mood_alive
    router.handle("un'altra")
    assert router._unmatched, "«un'altra» should mean nothing again"


def test_another_one_alone_means_nothing(router, library):
    reply = router.handle("un'altra")
    assert router._unmatched
    assert not any(cmd[0] == "genres" for cmd in library.commands())


# -- the honest misses --------------------------------------------------------

def test_a_mood_with_nothing_to_offer_hands_the_phrase_back(router, transport):
    # An empty mood is not an answer. It has to fall through, or a phrase the
    # rest of the router could still have handled dies here.
    transport.responses["genres"] = {"genres_loop": []}
    reply = router.handle("metti qualcosa di rilassante", source="local")
    assert not reply.ok
    assert "qualcosa di rilassante" in str(reply), (
        "the phrase should have gone on to be searched for")
    assert router.mood is None


def test_a_band_named_after_a_mood_is_still_searched_for(router, transport,
                                                         make_tidal):
    # "play some Fun" names a band; 'fun' is also a mood word. An empty mood
    # must not be the reason the band stops being looked for.
    transport.responses["genres"] = {"genres_loop": []}
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Some Nights",
                      "artist": "Fun"}]},
    )
    reply = router.handle("play some Fun", lang="en", source="tidal")
    assert reply.ok, str(reply)
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


def test_an_unreachable_server_is_not_a_missing_mood(router, transport):
    transport.raise_on.add("genres")
    reply = router.handle("metti qualcosa di rilassante")
    assert str(reply) == (
        "Non riesco a contattare l'impianto in questo momento. Riprova tra poco.")
    assert not reply.ok


# -- kid-safe -----------------------------------------------------------------

def test_a_blocked_genre_is_not_offered(lms, library):
    from actions import Guard
    library.responses["genres"] = {"genres_loop": [
        {"id": 7, "genre": "Metal"}, {"id": 1, "genre": "Rock"}]}
    guard = Guard(restricted=True, blocklist=["metal"])
    reply = moods.play_mood(lms, "energetic", guard=guard)
    assert "Rock" in str(reply)
    assert played_genre(library) == "1"


def test_a_blocked_playlist_is_not_offered(lms, transport, make_tidal):
    from actions import Guard
    transport.responses["genres"] = {"genres_loop": []}
    transport.responses["tidal"] = make_tidal(
        categories={"Playlists": "P"},
        items={"P": [{"id": "bad", "name": "Explicit Party"},
                     {"id": "ok", "name": "Dance Party"}]},
    )
    guard = Guard(restricted=True, blocklist=["explicit"])
    reply = moods.play_mood(lms, "party", stream=lms.for_service("tidal"),
                            guard=guard)
    assert "Dance Party" in str(reply)


# -- the double filter: what must NOT become a mood ---------------------------

def test_a_named_song_is_not_a_mood(router, library, make_tidal):
    library.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc",
                      "name": "Bollicine"}]},
    )
    reply = router.handle("metti Bollicine di Vasco", source="tidal")
    assert "Bollicine" in str(reply)
    assert router.mood is None
    assert not any(cmd[0] == "genres" for cmd in library.commands())


def test_a_named_artist_clears_the_marker_and_still_is_not_a_mood(router, library):
    # «metti la musica di Vasco Rossi» DOES match the mood pattern — "la
    # musica" is the marker. The second filter is what saves it: "vasco rossi"
    # is not a mood word, so it goes on to the artist path untouched.
    pack = PACKS["it"]
    assert pack.PATTERNS["mood"].search("metti la musica di Vasco Rossi")
    reply = router.handle("metti la musica di Vasco Rossi")
    assert str(reply) == "Non ho trovato l'artista Vasco Rossi."
    assert router.mood is None


def test_a_song_named_after_a_mood_is_still_a_song(router, library, make_tidal):
    # The other half of the filter, and the only case where it does the work
    # alone: "blues" IS a mood word, so what keeps «metti Blues» a search is
    # the marker noun the phrase does not carry.
    library.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Blues"}]},
    )
    reply = router.handle("metti Blues", source="tidal")
    assert "Riproduco Blues" in str(reply)
    assert router.mood is None
    assert not any(cmd[0] == "genres" for cmd in library.commands())


def test_a_queued_transport_word_still_queues(router, library, make_tidal):
    # The regression T2.1 already paid for once: queue patterns run before
    # moods, so adding a mood step above them must not have moved this.
    library.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Stop"}]},
    )
    reply = router.handle("aggiungi Stop alla coda", source="tidal")
    assert "coda" in str(reply)
    assert ["playlist", "add", "tidal://1.flc"] in library.commands()


def test_skipping_a_track_still_skips_while_a_mood_plays(router, library):
    router.handle("metti qualcosa di rilassante")
    reply = router.handle("prossima")
    assert str(reply) == "Brano successivo."


def test_a_mood_into_the_queue_is_not_supported(router, library, make_tidal):
    # Documented as out of scope: the phrase keeps behaving the way it did
    # before this feature existed (a search for a song by that name).
    library.responses["tidal"] = make_tidal(categories={"Songs": "S"}, items={})
    reply = router.handle("aggiungi qualcosa di rilassante alla coda",
                          source="tidal")
    assert not reply.ok
    assert router.mood is None


@pytest.mark.parametrize("phrase", [
    "ferma la musica classica",
    "togli la musica classica",
    "spegni la musica classica",
    "basta con la musica classica",
    "non voglio musica classica",
])
def test_asking_to_stop_the_music_never_starts_it(router, library, phrase):
    # The hole the marker-plus-mood-word filter left wide open: every one of
    # these carries a marker ("la musica") and a mood word ("classica"), and
    # the mood step sits above the transport block — so a phrase asking to STOP
    # the music started it, and «ferma la musica classica» was a demonstrable
    # regression against the pause that used to work. The anchor is what closes
    # it: none of these begins with a request to play.
    library.responses["genres"] = {"genres_loop": [{"id": 9, "genre": "Classica"}]}
    router.handle(phrase)
    assert not any(cmd[0] == "playlistcontrol" for cmd in library.commands()), phrase


def test_pausing_still_pauses(router, library):
    # The other half of the pair: «ferma la musica» has to keep working, or the
    # fix above would have been a fix by amputation.
    assert str(router.handle("ferma la musica")) == "In pausa."


@pytest.mark.parametrize("phrase,expected", [
    ("metti l'album Musica Rilassante", "Non ho trovato l'album Musica Rilassante."),
    ("riproduci la playlist Musica Rilassante",
     "Non ho trovato la playlist Musica Rilassante."),
])
def test_a_request_that_names_what_it_wants_keeps_it(router, library, phrase,
                                                     expected):
    # "Musica Rilassante" is what people actually call their own playlists, and
    # the listener said the word "album"/"playlist": the request is identified
    # by definition, so the mood must not take it.
    assert str(router.handle(phrase)) == expected
    assert router.mood is None


@pytest.mark.parametrize("phrase", ["blocca musica triste", "sblocca musica triste"])
def test_a_parental_block_never_plays_what_it_forbids(lms, library, phrase):
    # kidsafe=None is the plain AGPL build, where block_add/block_remove are
    # not even checked — so this used to answer a parent trying to forbid
    # something by playing exactly that.
    library.responses["genres"] = {"genres_loop": [{"id": 7, "genre": "Blues"}]}
    Router(lms).handle(phrase)
    assert not any(cmd[0] == "playlistcontrol" for cmd in library.commands())


@pytest.mark.parametrize("phrase", ["cambia canzone", "un'altra canzone",
                                    "cambia volume"])
def test_skip_shaped_phrases_do_not_re_roll_the_mood(router, library, phrase):
    # «cambia canzone» means the same as «la prossima», which mood_another
    # claims to exclude — and did not, until it had to be the whole phrase.
    router.handle("metti qualcosa di energico")
    before = len(library.commands())
    router.handle(phrase)
    assert not any(cmd[0] == "playlistcontrol"
                   for cmd in library.commands()[before:]), phrase


def test_a_room_targeted_mood_re_rolls_in_that_room(lms, library):
    from conftest import FakeLicense
    from pro.multiroom import MultiRoom
    players = [{"playerid": "aa:aa", "name": "Salotto"},
               {"playerid": "bb:bb", "name": "Cucina"}]
    router = Router(lms, multiroom=MultiRoom(FakeLicense(pro=True),
                                             lambda: players))
    router.handle("metti qualcosa di energico in cucina")
    reply = router.handle("un'altra")
    loads = [player for player, cmd in library.calls
             if cmd[0] == "playlistcontrol"]
    assert loads == ["bb:bb", "bb:bb"], (
        "a re-roll must not start music in a room nobody asked for")
    assert "Cucina" in str(reply), "and it has to say where"


def test_the_room_tag_lands_in_the_sentence_that_means_something(lms, library):
    from conftest import FakeLicense
    from pro.multiroom import MultiRoom
    players = [{"playerid": "bb:bb", "name": "Cucina"}]
    router = Router(lms, multiroom=MultiRoom(FakeLicense(pro=True),
                                             lambda: players))
    reply = router.handle("metti qualcosa di energico in cucina")
    # Not "... dimmi un'altra in Cucina.", which reads as an instruction about
    # where to stand when you say it.
    assert str(reply).startswith("Ho messo un po' di Rock in Cucina.")


# -- the double filter, second pass: what the new vocabulary must NOT take -----

# Every entry added to MOOD_WORDS widens the set of tails that stop being a
# title, which is why the bare nouns are absent: «natale» is «Bianco Natale»
# and «estate» is Vivaldi and De Andre at once. These are the phrases that got
# riskier when christmas/instrumental/summer were added, and the two English
# families at the end are the exact bugs the T2.4 review found - the `^` anchor
# is what covers them, and this is the test that keeps it there.

@pytest.mark.parametrize("phrase", [
    "metti Bianco Natale",
    "metti l'album Musica Strumentale",
    "metti Estate di De Andre",
    # The collision that decided against adding a bare «natale» to the table.
    # Natale is a real artist's name (Natale Galletta), step 0c runs BEFORE the
    # `artist` pattern, and the pattern eats the «di» - so a bare entry would
    # take this phrase away from the artist path for good. It reaches the
    # search today; this is what says so out loud.
    "metti la musica di Natale",
    # Same table entry, the other half of the damage: «playlist» makes this an
    # identified request by definition, and «Natale in Famiglia» is a name
    # people really give their own playlists.
    "metti la playlist Natale in Famiglia",
    "ferma la musica natalizia",
    "togli la musica natalizia",
    "blocca musica natalizia",
    "non voglio musica natalizia",
    # Same, in Italian: "dagli anni ottanta in poi" contains "dagli anni
    # ottanta" and means something else entirely.
    "metti qualcosa dagli anni ottanta in poi",
])
def test_the_new_words_do_not_swallow_a_title_or_a_stop(router, decades, phrase):
    # A library that can answer every one of the new moods, so a phrase that
    # wrongly became one would demonstrably start music instead of quietly
    # coming up empty.
    decades.responses["genres"] = {"genres_loop": [
        {"id": 8, "genre": "Christmas"}, {"id": 9, "genre": "Classical"},
        {"id": 10, "genre": "Reggae"}, {"id": 11, "genre": "Instrumental"}]}
    router.handle(phrase)
    assert not loads(decades), phrase
    assert router.mood is None, phrase


@pytest.mark.parametrize("phrase", [
    "play Summer of '69",
    # The whole-tail rule, which the new vocabulary is what makes testable:
    # "summer of 69" CONTAINS "summer", and a lookup that scanned for a
    # substring instead of hitting the whole tail would take the song.
    "play some Summer of '69",
    # The phrase that got a bare "summer" removed from the table. It carries a
    # marker, so the marker alone would not have saved it: the only thing that
    # keeps this a search for the Calvin Harris track is that "summer" is not
    # a mood word. Re-adding it breaks exactly this line.
    "put on some Summer",
    "stop playing something instrumental",
    "i don't want something instrumental",
    "don't play christmas music",
    "block christmas music",
])
def test_the_new_words_do_not_swallow_a_title_or_a_stop_in_english(
        router, decades, phrase):
    # A library that can answer every one of the new moods, so a phrase that
    # wrongly became one would demonstrably start music instead of quietly
    # coming up empty.
    decades.responses["genres"] = {"genres_loop": [
        {"id": 8, "genre": "Christmas"}, {"id": 9, "genre": "Classical"},
        {"id": 10, "genre": "Reggae"}, {"id": 11, "genre": "Instrumental"}]}
    router.handle(phrase, lang="en")
    assert not loads(decades), phrase
    assert router.mood is None, phrase


# The bare nouns, refused on purpose. Nothing else in this file can catch them:
# they are only reachable through a phrase that IS a mood request, so the test
# has to be about the table. «natale» on its own is «Bianco Natale», «estate»
# is Vivaldi and De Andre at once, and either one turns a title into a mood the
# moment somebody says «metti qualcosa di ...». The cost is a known gap, and it
# is the cheaper half: «metti musica di natale» arrives here as the bare
# "natale" (the pattern eats the "di") and therefore does not work - «musica
# natalizia» and «musica per natale» do.
#
# Adding «natale» was reconsidered in review and refused on evidence, not on
# caution. It buys no corpus phrase (coverage is 112/136 either way, because
# «musica natalizia» already covers the Italian christmas line) and it costs
# two things: «metti la musica di Natale» stops reaching the artist Natale
# Galletta by any phrasing of that shape, and the family splits in half -
# «metti le canzoni di Natale» would still be an artist search, because the
# marker list has «canzoni» but not «le canzoni». Two words apart, opposite
# behaviour, which is the same shape as the «ferma la musica classica» bug the
# T2.4 review caught. If the gap is ever closed it belongs in the pattern
# (stop eating «di» before a known mood word), not in this table.
@pytest.mark.parametrize("word", ["natale", "estate", "spiaggia", "parole",
                                  "anni", "strumenti"])
def test_the_bare_italian_nouns_are_not_mood_words(word):
    assert word not in PACKS["it"].MOOD_WORDS


@pytest.mark.parametrize("phrase", ["metti Anni 60", "play 80s"])
def test_a_bare_decade_without_a_marker_is_still_a_title(router, decades, phrase):
    # "anni 60"/"80s" ARE mood words now. What keeps «metti Anni 60» a search
    # is the marker noun the phrase does not carry - the other half of the
    # filter, doing the work alone.
    lang = "it" if phrase.startswith("metti") else "en"
    router.handle(phrase, lang=lang, source="local")
    assert not loads(decades), phrase
    assert router.mood is None, phrase


# -- English ------------------------------------------------------------------

def test_a_mood_in_english(router, library):
    reply = router.handle("play something relaxing", lang="en")
    assert str(reply) == (
        "I've put on some Ambient. Say another one if it doesn't fit.")


def test_a_multi_word_mood_in_english(router, library):
    reply = router.handle("play some music for dinner", lang="en")
    assert "Jazz" in str(reply)


def test_a_trailing_noun_is_not_part_of_the_mood_in_english(router, library):
    # "some upbeat music" asks for `happy`, not for a mood called
    # "upbeat music".
    assert moods.match_mood(
        PACKS["en"].PATTERNS["mood"].search("play some upbeat music").group(1),
        PACKS["en"].MOOD_WORDS) == "happy"


def test_another_one_in_english(router, library):
    router.handle("play something energetic", lang="en")
    reply = router.handle("another one", lang="en")
    assert reply.ok


def test_next_is_never_another_one_in_english(router, library):
    # "next one" was deliberately left out of mood_another: while a mood
    # plays, skipping a track still has to be skipping a track.
    router.handle("play something relaxing", lang="en")
    reply = router.handle("next", lang="en")
    assert str(reply) == "Next track."


@pytest.mark.parametrize("phrase", ["stop playing something sad",
                                    "i don't want something sad",
                                    "don't play something sad"])
def test_asking_not_to_play_never_plays_in_english(router, library, phrase):
    library.responses["genres"] = {"genres_loop": [{"id": 7, "genre": "Blues"}]}
    router.handle(phrase, lang="en")
    assert not any(cmd[0] == "playlistcontrol" for cmd in library.commands()), phrase


def test_another_one_alone_means_nothing_in_english(router, library):
    router.handle("another one", lang="en")
    assert router._unmatched


def test_a_named_song_is_not_a_mood_in_english(router, library, make_tidal):
    library.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc",
                      "name": "Bohemian Rhapsody"}]},
    )
    reply = router.handle("play Bohemian Rhapsody", lang="en", source="tidal")
    assert "Bohemian Rhapsody" in str(reply)
    assert router.mood is None


# -- the residue (the number T2.5 is decided on) ------------------------------

def test_the_corpus_is_answered_or_knowingly_out_of_reach():
    """T2.4's acceptance criterion asks how much stays unanswered.

    The honest framing, because it is easy to overstate: the corpus was written
    first, as people speak, and the vocabulary was then widened to catch four
    phrases it missed — so the covered half is not an independent measurement.
    The residue is, and it is the part that matters: every phrase left over
    needs something strada A does not have. See tools/mood_coverage.py for the
    breakdown and .omc/plans/vivavoce-roadmap.md for what it decides.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools"))
    import mood_coverage

    for lang in ("it", "en"):
        covered, residual = mood_coverage.coverage(lang)
        total = len(covered) + len(residual)
        assert total >= 60, f"{lang}: corpus too small to mean anything"
        # A floor, not a target: it is here to catch a regression that quietly
        # stops answering half the corpus, not to be tuned upwards.
        assert len(covered) / total >= 0.70, (
            f"{lang}: coverage fell to {len(covered)}/{total} — "
            f"still unanswered: {[p for p, _ in residual]}")
