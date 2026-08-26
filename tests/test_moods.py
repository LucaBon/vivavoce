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


def played_genre(transport):
    """The genre_id the router loaded, or None."""
    for cmd in transport.commands():
        if cmd[:2] == ["playlistcontrol", "cmd:load"]:
            for part in cmd[2:]:
                if part.startswith("genre_id:"):
                    return part[len("genre_id:"):]
    return None


# -- the table itself ---------------------------------------------------------

def test_every_mood_offers_both_a_genre_and_a_playlist():
    # A mood with only one of the two has only one of the two fallbacks, and
    # would fail silently for exactly the listeners who don't have the other.
    for key, mood in moods.MOODS.items():
        assert mood["genres"], f"{key} has no genre aliases"
        assert mood["playlists"], f"{key} has no playlist queries"


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
