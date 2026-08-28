"""Tests for the P0 reliability layer: fuzzy scoring / best-pick, confidence
gating with a 'did you mean' fallback, the structured ActionResult (.ok /
.candidates), artist confirmation, and language-independent TIDAL categories.

These cover behaviour that the older first-hit-wins tests did not: multi-candidate
ranking and the disambiguation prompt."""

import pytest

import actions
from actions import ActionResult, _score
from messages import set_lang


# -- _score ---------------------------------------------------------------
def test_score_exact_and_accent_insensitive():
    assert _score("Time", "time") == 1.0
    assert _score("Andrà", "andra") == 1.0


def test_score_subset_either_direction_is_strong():
    # every requested word present in the title
    assert _score("time", "Time (Remastered 2011)") >= 0.9
    # whole title present in the request (user appended the artist)
    assert _score("comfortably numb pink floyd", "Comfortably Numb") >= 0.9


def test_score_unrelated_is_low():
    assert _score("qualcosa", "Alpha") < actions.CONFIDENT_SCORE


# -- best-pick instead of blind first -------------------------------------
def test_play_song_picks_best_scoring_not_first(lms, transport, make_tidal):
    # TIDAL returns 'Money for Nothing' first, but the exact 'Money' must win.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Money for Nothing"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"},
            ]
        },
    )
    msg = actions.play_song(lms, "money")
    assert msg == "Riproduco Money."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


def test_play_song_confirms_artist_when_known(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Time", "artist": "Pink Floyd"}
            ]
        },
    )
    assert actions.play_song(lms, "time") == "Riproduco Time di Pink Floyd."


def test_play_song_enriches_artist_from_now_playing(lms, transport, make_tidal):
    # TIDAL search has no artist, but now-playing does -> confirm with it.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Like a Stone"}]},
    )
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Like a Stone", "artist": "Audioslave"}]
    }
    assert actions.play_song(lms, "Audioslave") == "Riproduco Like a Stone di Audioslave."


def test_play_song_ignores_stale_now_playing_artist(lms, transport, make_tidal):
    # If status still shows a DIFFERENT (previous) track, don't misattribute it.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Like a Stone"}]},
    )
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Qualcos'altro", "artist": "Altro"}]
    }
    assert actions.play_song(lms, "Audioslave") == "Riproduco Like a Stone."


def test_play_song_appended_artist_still_plays(lms, transport, make_tidal):
    # "Comfortably Numb Pink Floyd" — title is just 'Comfortably Numb'; must not
    # be treated as ambiguous just because 'pink floyd' isn't in the title.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Comfortably Numb"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Hey You"},
            ]
        },
    )
    msg = actions.play_song(lms, "Comfortably Numb Pink Floyd")
    assert msg == "Riproduco Comfortably Numb."
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


# -- artist-name / loose query: trust TIDAL's order (field-tested regression) --
def test_artist_name_query_plays_tidal_top_not_reordered(lms, transport, make_tidal):
    # "Audioslave"/"Pink Floyd" as a song query: no track TITLE matches, every
    # score is noise. Must play TIDAL's #1, not reorder to a random high-noise one.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Like a Stone"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Cochise"},
                {"isaudio": 1, "url": "tidal://3.flc", "name": "Gasoline"},
            ]
        },
    )
    assert actions.play_song(lms, "Audioslave") == "Riproduco Like a Stone."
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


def test_identical_titles_do_not_ask(lms, transport, make_tidal):
    # Several editions of the same song all score 1.0/0.95: don't offer a useless
    # "1: X, 2: X, 3: X" list — dedup to one and play TIDAL's top.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Comfortably Numb"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Comfortably Numb"},
                {"isaudio": 1, "url": "tidal://3.flc", "name": "Comfortably Numb"},
            ]
        },
    )
    msg = actions.play_song(lms, "Comfortably Numb Pink Floyd")
    assert msg == "Riproduco Comfortably Numb."
    assert msg.candidates == []  # not a disambiguation
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


# -- artist named -> play the right edition (artist comes from the search) ------
def test_artist_given_picks_matching_edition(lms, transport, make_tidal):
    # Two identical "Comfortably Numb" titles; the parsed artist picks Pink Floyd's.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Comfortably Numb",
                 "artist": "The Australian Pink Floyd Show"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Comfortably Numb",
                 "artist": "Pink Floyd"},
            ]
        },
    )
    msg = actions.play_song(lms, "Comfortably Numb dei Pink Floyd")
    assert msg == "Riproduco Comfortably Numb di Pink Floyd."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


def test_tidal_did_you_mean_then_choose(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Another Brick in the Wall, Pt. 1"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Another Brick in the Wall, Pt. 2"},
            ]
        },
    )
    prompt = actions.play_song(lms, "brick")
    assert actions.choose_from(lms, prompt.candidates, 2) == (
        "Riproduco Another Brick in the Wall, Pt. 2."
    )
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


def test_local_did_you_mean_then_choose(lms, transport):
    # Local rows carry the artist, so the list reads "Love di X, Love di Y".
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {
        "titles_loop": [
            {"id": 1, "title": "Love", "artist": "Kendrick Lamar"},
            {"id": 2, "title": "Love", "artist": "Nat King Cole"},
        ]
    }
    msg = actions.play_local(lms, "love")
    assert msg.kind == "disambiguate"
    assert "1: Love di Kendrick Lamar" in msg and "2: Love di Nat King Cole" in msg
    assert actions.choose_from(lms, msg.candidates, 2) == "Riproduco Love."
    assert ["playlistcontrol", "cmd:load", "track_id:2"] in transport.commands()


# -- genuinely distinct partial matches -> ask the top 3 -----------------------
def test_partial_query_asks_when_distinct(lms, transport, make_tidal):
    # "brick" matches two *different* songs; ask instead of guessing.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Another Brick in the Wall, Pt. 1"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Another Brick in the Wall, Pt. 2"},
            ]
        },
    )
    msg = actions.play_song(lms, "brick")
    assert isinstance(msg, ActionResult) and msg.kind == "disambiguate"
    assert "1: Another Brick in the Wall, Pt. 1" in msg
    assert [c["url"] for c in msg.candidates] == ["tidal://1.flc", "tidal://2.flc"]
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_padded_junk_title_does_not_win(lms, transport, make_tidal):
    # A novelty track whose title CONTAINS all query words is ranked low by TIDAL,
    # so it never reaches the top-3 shortlist; the clean editions collapse to one.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Comfortably Numb"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Comfortably Numb"},
                {"isaudio": 1, "url": "tidal://3.flc", "name": "Comfortably Numb"},
                {"isaudio": 1, "url": "tidal://9.flc",
                 "name": "Popping: No. 19, Lobotomized Pink Floyd Comfortably Numb"},
            ]
        },
    )
    msg = actions.play_song(lms, "Comfortably Numb Pink Floyd")
    assert msg == "Riproduco Comfortably Numb."
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()
    assert ["playlist", "play", "tidal://9.flc"] not in transport.commands()


# -- ActionResult.ok flags ------------------------------------------------
def test_ok_flag_on_hit_and_miss(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    assert actions.play_song(lms, "time").ok is True
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"}, items={"S": []})
    assert actions.play_song(lms, "x").ok is False


# -- play_album best-pick (edition) ---------------------------------------
def test_play_album_picks_matching_edition(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "AL"},
        items={
            "AL": [
                {"type": "playlist", "id": "A1", "name": "The Wall"},
                {"type": "playlist", "id": "A2", "name": "The Wall Live In Berlin"},
            ]
        },
    )
    actions.play_album(lms, "The Wall Live In Berlin")
    assert ["tidal", "playlist", "play", "item_id:A2"] in transport.commands()


# -- _play_from_album scored matching -------------------------------------
def test_play_from_album_partial_title_scored(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "AL"},
        items={
            "AL": [{"type": "playlist", "id": "ALB", "name": "The Wall"}],
            "ALB": [{"isaudio": 1, "url": "tidal://2.flc", "name": "Comfortably Numb"}],
        },
    )
    msg = actions.play_song(lms, "Numb dall'album The Wall")
    assert msg == "Riproduco Comfortably Numb dall'album The Wall."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


# -- language-independent TIDAL categories --------------------------------
def test_search_works_with_italian_category_name(lms, transport, make_tidal):
    # LMS UI in Italian returns 'Brani' instead of 'Songs' -> still resolves.
    transport.responses["tidal"] = make_tidal(
        categories={"Brani": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    assert lms.search_tracks("time") == [{"url": "tidal://1.flc", "title": "Time"}]


# -- terms carried for multilingual read-back (web app reads names in-language) --
def test_play_song_carries_title_and_artist_terms(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Like a Stone"}]},
    )
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Like a Stone", "artist": "Audioslave"}]
    }
    res = actions.play_song(lms, "Audioslave")
    assert res.terms == ["Like a Stone", "Audioslave"]


def test_play_song_terms_title_only_without_artist(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    assert actions.play_song(lms, "time").terms == ["Time"]


def test_play_album_carries_album_term(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "AL"},
        items={"AL": [{"type": "playlist", "id": "ALB", "name": "The Wall"}]},
    )
    assert actions.play_album(lms, "the wall").terms == ["The Wall"]


def test_now_playing_carries_terms(lms, transport):
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": "Pink Floyd"}]
    }
    assert actions.now_playing(lms).terms == ["Time", "Pink Floyd"]


def test_play_local_carries_term(lms, transport):
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]
    }
    assert actions.play_local(lms, "90125").terms == ["90125"]


# -- local library must not play loose/irrelevant matches (field-tested) --------
def test_play_local_rejects_irrelevant_album(lms, transport):
    # "love" -> LMS returns an unrelated album; scoring rejects it (would have
    # silently played "Hotel California" before).
    transport.responses["albums"] = {
        "albums_loop": [{"id": 1, "album": "Hotel California", "artist": "Eagles"}]
    }
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {"count": 0}
    res = actions.play_local(lms, "love")
    assert res.ok is False and "Non ho trovato" in res
    assert not any(c[:2] == ["playlistcontrol", "cmd:load"] for c in transport.commands())


def test_play_local_rejects_substring_only_match(lms, transport):
    # "love" is a substring of "Be My Lover" but not a real word match -> reject.
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {"titles_loop": [{"id": 9, "title": "Be My Lover"}]}
    assert actions.play_local(lms, "love").ok is False


def test_play_local_artist_query_plays_artist(lms, transport):
    # "Aerosmith" matches the ARTIST by name; the album matches only via its artist
    # field (not title), so we play the artist, not one of their albums.
    transport.responses["artists"] = {"artists_loop": [{"id": 1158, "artist": "Aerosmith"}]}
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "Toys in the Attic", "artist": "Aerosmith"}]
    }
    transport.responses["titles"] = {"count": 0}
    assert actions.play_local(lms, "Aerosmith") == "Riproduco Aerosmith dalla tua musica."
    assert ["playlistcontrol", "cmd:load", "artist_id:1158"] in transport.commands()


def test_play_local_strips_leading_filler(lms, transport):
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]
    }
    assert actions.play_local(lms, "la canzone 90125") == (
        "Riproduco l'album 90125 dalla tua musica."
    )


def test_play_song_strips_leading_filler(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    assert actions.play_song(lms, "la canzone Time") == "Riproduco Time."


def test_control_reply_has_no_terms(lms, transport):
    # Fully-Italian replies carry nothing to re-voice.
    assert list(getattr(actions.pause(lms), "terms", [])) == []


def test_search_tracks_includes_artist_when_present(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={
            "S": [
                {"isaudio": 1, "url": "tidal://1.flc", "name": "Time", "artist": "PF"},
                {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"},  # no artist
            ]
        },
    )
    assert lms.search_tracks("x") == [
        {"url": "tidal://1.flc", "title": "Time", "artist": "PF"},
        {"url": "tidal://2.flc", "title": "Money"},
    ]


# -- normalisation: punctuation used to decide matches ------------------------
def test_punctuation_does_not_defeat_a_title():
    # Measured before the fix: 0.089 — «wall» could not find this song at all.
    assert _score("wall", "Another Brick in the Wall, Pt. 1") >= 0.9


def test_a_dropped_apostrophe_still_matches():
    # Web Speech writes «dont», and Italian is full of l'/dell'. This scored
    # 0.84 — below EXACT_SCORE, so it asked "which one?" instead of playing.
    assert _score("dont stop me now", "Don't Stop Me Now") == 1.0
    assert _score("Don’t Stop Me Now", "Don't Stop Me Now") == 1.0
    assert _score("l'amore", "lamore") == 1.0


def test_letters_without_a_combining_mark_are_folded_too():
    assert actions._normalize("Straße") == "strasse"
    assert actions._normalize("Sigur Rós") == "sigur ros"
    assert actions._normalize("Motörhead") == "motorhead"


def test_non_latin_titles_keep_their_characters():
    assert actions._normalize("Полюшко Поле") == "полюшко поле"


# -- the artist separator -----------------------------------------------------
def test_the_last_connector_splits_title_from_artist():
    # Split on the FIRST "by" and this searched for a song called "Stand".
    # Said in English, so parsed in English: «by» is English's connector and
    # nobody else's (engine/connectors/en.py).
    assert actions.parse_song_query("Stand By Me by Ben E. King", lang="en") == {
        "title": "Stand By Me", "artist": "Ben E. King", "album": None}


def test_a_connector_inside_a_title_is_not_an_artist():
    assert actions.parse_song_query("Ti amo di più")["artist"] is None


def test_a_leading_connector_left_by_the_filler_is_dropped():
    assert actions.parse_song_query("la canzone di Marinella di De André") == {
        "title": "Marinella", "artist": "De André", "album": None}


def test_an_elided_connector_still_needs_its_space():
    # «dell'» is a connector only with a space after it. The tables were one
    # shared pile until French needed its own; moving each alternative's
    # whitespace inside it turned this into `dell['’]\s*`, and every elided
    # Italian title started splitting — «Il canto dell'amore» went looking for
    # a singer called «amore». Pinned here because no other test spells an
    # elided title out.
    for title in ("Il canto dell'amore", "Storia dell'arte", "La donna dell'est"):
        assert actions.parse_song_query(title) == {
            "title": title, "artist": None, "album": None}


def test_a_title_that_opens_with_a_connector_keeps_its_first_word():
    # The strip above used to run unconditionally, so any request that merely
    # STARTED with a connector lost its first word: «By the Way» searched TIDAL
    # for "the Way" and «Della vita» for "vita". It may only fire when the lead
    # filler actually removed something.
    # Each under the language whose connector it opens with, or the assertion
    # is vacuous: «By the Way» has nothing to strip when parsed as Italian.
    assert actions.parse_song_query("By the Way", lang="en")["title"] == "By the Way"
    assert actions.parse_song_query("Della vita")["title"] == "Della vita"
    assert actions.parse_song_query("Di Nuovo Insieme")["title"] == "Di Nuovo Insieme"
    assert actions.parse_song_query("By the Way", lang="en")["artist"] is None


# Each row under the language it is a title in: «by» is English's connector
# now, so the three English rows invent nothing at all under Italian and would
# stop testing the invention this guards against.
@pytest.mark.parametrize("lang, query, title", [
    ("it", "Cuore di Vetro", "Cuore di Vetro"),
    ("it", "Nel Blu Dipinto di Blu", "Nel Blu Dipinto di Blu"),
    ("it", "Il Ragazzo della Via Gluck", "Il Ragazzo della Via Gluck"),
    ("it", "Notte Prima degli Esami", "Notte Prima degli Esami"),
    ("it", "Fiume di Fango", "Fiume di Fango"),
    ("en", "Killed by Death", "Killed by Death"),
    ("en", "Blinded by the Light", "Blinded by the Light"),
    ("en", "Stand By Your Man", "Stand By Your Man"),
])
def test_a_title_containing_a_connector_still_plays(lang, query, title, lms,
                                                    transport, make_tidal):
    # The split on the LAST connector invents an artist for any title that
    # merely contains one («Cuore di Vetro» -> 'Cuore' by 'Vetro'). That used to
    # degrade gracefully; once the "nobody in the results is them" refusal
    # existed it turned into a hard "non ho trovato" with the exact track
    # sitting first in the results — and ok=False made handle_many burn the
    # next ASR alternative on top.
    set_lang(lang)
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://ok.flc", "name": title,
                      "artist": "Un Artista"}]},
    )
    reply = actions.play_song(lms, query)
    assert reply.ok is True
    assert ["playlist", "play", "tidal://ok.flc"] in transport.commands()


def test_a_connector_title_matches_a_padded_edition(lms, transport, make_tidal):
    # The un-split must survive the suffixes TIDAL actually ships.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://r.flc",
                      "name": "Cuore di Vetro (Remastered 2012)",
                      "artist": "Matia Bazar"}]},
    )
    reply = actions.play_song(lms, "Cuore di Vetro")
    assert reply.ok is True
    assert ["playlist", "play", "tidal://r.flc"] in transport.commands()


# -- a named artist that isn't in the results ---------------------------------
def test_a_named_artist_with_no_edition_is_not_silently_swapped(
        lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc",
                      "name": "Yesterday", "artist": "The Beatles"}]},
    )
    reply = actions.play_song(lms, "Yesterday di Vasco Rossi")
    assert reply.ok is False
    assert "Vasco Rossi" in reply
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_the_named_artist_is_found_below_the_top_three(lms, transport,
                                                       make_tidal):
    # Only the top 3 were scanned; the right edition often sits lower.
    items = [{"isaudio": 1, "url": f"tidal://{i}.flc", "name": "Yesterday",
              "artist": "A Cover Band"} for i in range(1, 6)]
    items.append({"isaudio": 1, "url": "tidal://real.flc",
                  "name": "Yesterday", "artist": "The Beatles"})
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"},
                                              items={"S": items})
    reply = actions.play_song(lms, "Yesterday dei Beatles")
    assert reply.ok is True
    assert ["playlist", "play", "tidal://real.flc"] in transport.commands()


# -- the dry run the room gate needs (T2.7b) -----------------------------------
#
# Every resolver in actions.py answers by *playing* something, so there was no
# way to ask "does the library know this phrase?" without music starting. The
# room gate has to ask exactly that, twice, before it decides whether «in
# america» is a room or the end of a title.

def test_score_subset_floor_can_be_switched_off():
    # With the floor on, every phrase that merely contains a title lands on the
    # same 0.95 and two phrasings cannot be told apart. Off, they separate.
    assert _score("breakfast", "Breakfast in America") == 0.95
    assert _score("breakfast", "Breakfast in America", subset_floor=False) < 0.9
    assert _score("breakfast in america", "Breakfast in America",
                  subset_floor=False) == 1.0


def test_library_candidates_never_plays_anything(lms, transport):
    transport.responses["albums"] = {"albums_loop": [{"id": 10, "album": "Bollicine"}]}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {"count": 0}
    cands = actions.library_candidates(lms, "bollicine")
    assert [c["title"] for c in cands] == ["Bollicine"]
    assert all(cmd[0] in ("albums", "artists", "titles")
               for cmd in transport.commands()), transport.commands()


def test_library_candidates_costs_three_queries(lms, transport):
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {"count": 0}
    actions.library_candidates(lms, "bollicine")
    assert len(transport.calls) == 3


def test_library_candidates_on_lms_error_is_empty(lms, transport):
    transport.raise_on.add("albums")
    assert actions.library_candidates(lms, "bollicine") == []


def test_library_candidates_of_nothing_asks_nothing(lms, transport):
    assert actions.library_candidates(lms, "  ") == []
    assert transport.calls == []


def test_best_match_score_of_an_empty_pool_is_zero():
    assert actions.best_match_score("bollicine", []) == 0.0
    assert actions.best_match_score("bollicine", None) == 0.0


def test_best_match_score_takes_the_best_row():
    pool = [{"title": "Notte prima degli esami"}, {"title": "Bollicine"}]
    assert actions.best_match_score("bollicine", pool) == 1.0


def test_a_tagged_edition_still_clears_the_confidence_floor():
    # The margin this fix actually runs on in a real library. It is real but
    # not large: a longer tag drops the whole-phrase reading under the floor
    # and the room quietly wins again — safely (no action), but silently.
    tagged = [{"title": "Breakfast In America (2010 Remastered Deluxe Edition)"}]
    whole = actions.best_match_score("breakfast in america", tagged, subset_floor=False)
    room = actions.best_match_score("breakfast", tagged, subset_floor=False)
    assert whole >= actions.LOCAL_CONFIDENT
    assert whole > room
