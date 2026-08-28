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


# -- the separable verb, and the six ways it went wrong -----------------------
#
# Every test in this block was a defect found in review of the pack's first
# draft. They share one cause: German writes the second half of the verb after
# the object, so any pattern that captures "everything to the end" captures a
# word that is grammar, not a name — and any gate that looks for that half
# near the verb is really a length limit on titles.

def test_a_long_title_does_not_reopen_the_transport_block(router, transport,
                                                          make_tidal):
    """`is_play` measured the distance from «mach» to «an» in characters, so
    «mach die Playlist Zurück in die Zukunft an» — 32 of them — read as no
    play command at all, and «zurück» skipped to the previous track."""
    transport.responses["playlists"] = {"playlists_loop": [
        {"id": "p1", "playlist": "Zurück in die Zukunft"}]}
    router.handle("mach die Playlist Zurück in die Zukunft an",
                  source="tidal", lang="de")
    assert ["playlist", "index", "-1"] not in transport.commands()


@pytest.mark.parametrize(
    "phrase, wanted",
    [("mach das Album Dark Side an", "Dark Side"),
     ("leg das Album Nevermind auf", "Nevermind")],
)
def test_the_album_name_does_not_keep_the_particle(router, transport,
                                                   make_tidal, phrase, wanted):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": wanted, "hasitems": 1}]},
    )
    assert router.handle(phrase, source="tidal",
                         lang="de") == f"Ich spiele das Album {wanted} von TIDAL."


def test_the_playlist_name_does_not_keep_the_particle(router, transport, make_tidal):
    # Asserted through the miss, which echoes the name back: what is on trial
    # is the capture, and a "not found" says it exactly.
    transport.responses["tidal"] = make_tidal(categories={"Playlists": "P"},
                                              items={"P": []})
    speech = router.handle("leg die Playlist Chill auf", source="tidal", lang="de")
    assert speech == "Ich habe die Playlist Chill nicht gefunden."


def test_the_artist_name_does_not_keep_the_particle(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Nena", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://6.flc", "name": "99 Luftballons"}]},
    )
    router.handle("spiel Musik von Nena an", source="tidal", lang="de")
    assert ["playlist", "play", "tidal://6.flc"] in transport.commands()


@pytest.mark.parametrize("phrase", ["mach die Musik an", "mach das Radio an",
                                    "mach die Anlage an"])
def test_turning_the_music_on_is_a_resume_not_a_search(router, transport, phrase):
    """«mach die Musik an» names nothing: it is the German for pressing ▶.
    Read as a request it searched the library for the word «Musik», and
    «mach das Radio an» asked the favorites for a station called "an"."""
    assert router.handle(phrase, lang="de") == "Ich spiele weiter."
    assert transport.last_call()[1] == ["pause", "0"]


@pytest.mark.parametrize("phrase", ["spiel das Radio SWR3",
                                   "mach das Radio SWR3 an"])
def test_a_named_radio_station_still_reaches_the_radio_step(router, transport,
                                                            phrase):
    # Same shape as the playlist test: the miss quotes the station name, so it
    # proves the particle came off without needing a favorites feed.
    assert router.handle(phrase, lang="de") == (
        "Ich habe keinen Radiosender namens SWR3 in deinen Favoriten gefunden.")


@pytest.mark.parametrize("phrase", ["hör auf", "hör bitte auf"])
def test_hoer_auf_stops_instead_of_playing_a_song_called_auf(router, transport,
                                                             phrase):
    """The commonest German "stop" carries a play verb, so the is_play gate
    kept ``pause`` from ever seeing it and the phrase went looking for «auf»."""
    assert router.handle(phrase, lang="de") == "Pausiert."


def test_a_title_that_merely_contains_auf_still_plays(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://2.flc",
                      "name": "Hör auf dein Herz"}]},
    )
    router.handle("spiel Hör auf dein Herz", source="tidal", lang="de")
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()
    assert ["pause", "1"] not in transport.commands()


@pytest.mark.parametrize(
    "title, stolen",
    [("Ich gehöre nur mir", "nur mir"),      # «hör» lives inside «gehöre»
     ("Neustart der Nacht", "der Nacht")],   # «start» inside «Neustart»
)
def test_a_play_verb_does_not_match_inside_a_word(router, transport, make_tidal,
                                                  title, stolen):
    """German compounds put the verbs inside other words. Without a word
    boundary, a phrase carrying no play command at all matched ``generic_play``
    on a substring and searched for its own tail — «Ich gehöre nur mir» went
    looking for "nur mir". With one, the phrase names no command and the
    router says so, which is the same thing Italian and English do with a
    bare title and no open list."""
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"},
                                              items={"S": []})
    speech = router.handle(title, source="tidal", lang="de")
    assert speech.startswith("Das habe ich nicht verstanden.")
    assert stolen not in speech
    assert transport.commands() == []


@pytest.mark.parametrize("phrase", ["leg das Hörbuch auf", "leg Hörspiel auf",
                                    "leg die Hörprobe auf"])
def test_a_noun_built_on_the_stop_verb_is_not_a_stop(router, transport,
                                                     make_tidal, phrase):
    """German builds nouns on the same stem: «Hörbuch», «Hörspiel»,
    «Hörprobe». Spelling the verb's ending as ``\\w*`` made all three read as
    «hör … auf», and asking for an audiobook paused the player."""
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"},
                                              items={"S": []})
    speech = router.handle(phrase, source="tidal", lang="de")
    assert speech != "Pausiert."
    assert ["pause", "1"] not in transport.commands()


@pytest.mark.parametrize(
    "phrase",
    ["hör auf", "hör bitte auf", "hör jetzt endlich auf", "hör auf zu spielen",
     "hörst du auf", "hört auf"],
)
def test_the_split_stop_verb_stops(router, transport, phrase):
    assert router.handle(phrase, lang="de") == "Pausiert."


@pytest.mark.parametrize(
    "phrase",
    ["hör nicht auf zu spielen", "hör bitte nicht auf zu spielen",
     "hör nie auf zu spielen"],
)
def test_the_negated_stop_does_not_stop(router, transport, make_tidal, phrase):
    """«hör auf zu spielen» started life as an alternative of its own, matching
    that tail anywhere with no verb bound to it — so the negation rode straight
    through and "don't stop playing" paused the music. It is the same
    alternative as «hör auf» now, with an optional tail, and the negator has
    nowhere to sit."""
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"},
                                              items={"S": []})
    assert router.handle(phrase, source="tidal", lang="de") != "Pausiert."
    assert ["pause", "1"] not in transport.commands()


@pytest.mark.parametrize(
    "phrase, seconds",
    [("hör in 30 Minuten auf", "1800"),
     ("hör in einer Stunde auf zu spielen", "3600")],
)
def test_the_split_stop_verb_carries_a_timer_in_both_its_lengths(
        router, transport, phrase, seconds):
    """The longer tail is the one that got away: the timer step learned «… auf»
    and not «… auf zu spielen», so the phrase fell into the pause the same
    commit had just taught, and the music stopped at once instead of in an
    hour."""
    router.handle(phrase, lang="de")
    assert transport.last_call()[1] == ["sleep", seconds]


def test_the_timer_lookahead_does_not_backtrack_against_itself():
    """Two unbounded ``.*`` in sequence cost 3.3 s to match a 64 KB string.

    Asserted on the PATTERN, not through ``Router.handle``: the router now
    refuses anything over ``MAX_COMMAND_CHARS`` before a pattern sees it, so
    routing this string would measure the length check and certify nothing.
    Both guards matter and they are different — see
    ``tests/test_router_limits.py`` for the other one.
    """
    import time
    from lang import PACKS
    hostile = "in 1 minute " + "hör auf " * 8000 + "x"
    start = time.monotonic()
    PACKS["de"].PATTERNS["sleep"].search(hostile)
    assert time.monotonic() - start < 1.0


# «hör Wach Auf» is the case that pins the closed list: its gap is 14
# characters, so the character window this replaced admitted it. The long one
# is a guard rather than a pin — the window declined it too.
@pytest.mark.parametrize("phrase", ["hör Wach Auf", "spiel Hör Mal Wer Da Hämmert auf"])
def test_a_title_between_the_stop_verb_and_its_particle_is_not_a_stop(
        router, transport, make_tidal, phrase):
    """What may stand between «hör» and «auf» is a closed list of adverbs, not
    a span of characters. A character window decided this by the length of the
    title, which is the flaw `is_play` had and this pattern inherited."""
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"},
                                              items={"S": []})
    assert router.handle(phrase, source="tidal", lang="de") != "Pausiert."


def test_the_split_stop_verb_can_still_carry_a_timer(router, transport):
    """«hör in 30 Minuten auf» keeps its «auf» at the very end, where the
    one-word verbs in the sleep lookahead could not see it — so the phrase
    fell past the timer and paused at once instead."""
    router.handle("hör in 30 Minuten auf", lang="de")
    assert transport.last_call()[1] == ["sleep", "1800"]


@pytest.mark.parametrize(
    "phrase, expected_cmd",
    [("mach das Radio aus", ["pause", "1"]),
     # One adverb defeats an exact-final guard, which is why the guard is not
     # exact-final any more.
     ("mach das Radio bitte aus", ["pause", "1"]),
     ("mach das Radio ganz aus", ["pause", "1"]),
     ("mach das Radio leiser", ["mixer", "volume", "-5"]),
     ("mach das Radio lauter", ["mixer", "volume", "+5"]),
     ("mach das Radio an", ["pause", "0"]),
     ("mach den Radiosender an", ["pause", "0"]),
     ("spiel die Musik weiter", ["pause", "0"]),
     ("spiel das Radio weiter", ["pause", "0"])],
)
def test_a_control_word_after_radio_is_a_control_not_a_station(
        router, transport, phrase, expected_cmd):
    """The radio step runs before the transport block, so a bare control word
    after «Radio» used to reach LMS as a station name and answer «Ich habe
    keinen Radiosender namens aus gefunden»."""
    router.handle(phrase, lang="de")
    assert transport.last_call()[1] == expected_cmd
    assert not any("search:aus" in str(c) for c in transport.commands())


def test_a_typed_double_space_does_not_slip_past_the_radio_guard(router, transport):
    # The guard used to sit after a greedy ``\s+``, which can hand a space
    # back; nothing between the text box and the pattern collapses inner
    # whitespace, so «mach das radio  an» asked for a station named " an".
    router.handle("mach das radio  an", lang="de")
    assert transport.last_call()[1] == ["pause", "0"]


@pytest.mark.parametrize("phrase", ["mach Zurück auf", "mach Zurück in die Zukunft auf"])
def test_every_particle_the_suffix_form_accepts_counts_as_a_play(
        router, transport, make_tidal, phrase):
    """`is_play` anchored on «an» alone while ``generic_play_suffix`` accepts
    four particles, so «mach Zurück auf» left the transport block open and
    «zurück» skipped a track instead of playing the record."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://3.flc", "name": "Zurück"}]},
    )
    router.handle(phrase, source="tidal", lang="de")
    assert ["playlist", "index", "-1"] not in transport.commands()


def test_naming_what_it_is_gets_past_the_resume_shortcut(router, transport,
                                                         make_tidal):
    """«mach das Radio an» is ▶, which costs a record called exactly *Radio*
    (Rammstein, 2019). Saying what it is buys it back."""
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": "Radio", "hasitems": 1}]},
    )
    assert router.handle("mach das Album Radio an", source="tidal",
                         lang="de") == "Ich spiele das Album Radio von TIDAL."


# -- the invariant, asserted by construction ----------------------------------
#
# Five review rounds found the same shape: a guard was widened and the step
# that catches what it declines was not, so a phrase fell past every catcher
# to the play step and started a stream. The lists are shared now, and this is
# what makes the sharing enforceable — it is a cross product rather than a
# list of phrases, so the sixth gap fails here instead of shipping.

_DEV_VERBS = ["spiel", "spiele", "mach", "leg", "starte", "schalt"]
_DEV_ARTICLES = ["", "das ", "die ", "den ", "der "]
_DEV_NOUNS = ["radio", "radiosender", "musik", "anlage", "mucke"]
_DEV_ADVERBS = ["", "bitte ", "jetzt bitte ", "endlich wieder "]
_DEV_CONTROLS = ["an", "auf", "ab", "aus", "lauter", "leiser", "weiter",
                 "stopp", "stop"]


def _device_commands():
    for verb in _DEV_VERBS:
        for article in _DEV_ARTICLES:
            for noun in _DEV_NOUNS:
                for adverbs in _DEV_ADVERBS:
                    for control in _DEV_CONTROLS:
                        yield f"{verb} {article}{noun} {adverbs}{control}"


# The other direction, which the cross product above cannot see: a request
# that NAMES something must never be answered with a transport command. Both
# halves are needed and neither implies the other — the one-directional test
# shipped for one commit and, on its own, required «spiel die Musik ab» to
# mean stop, when ``abspielen`` is the German for "to play back".
_MUST_PLAY = [
    "spiel Musik aus Italien",
    "spiel den Song Mach die Musik aus",     # a title that IS a device command
    "spiel den Titel Mach die Musik lauter",
    "spiel Wir spielen Musik ab",
    "spiel Radiohead",
    "starte Radioaktivität",
    "spiel Anlage 12",
    "spiel Mucke für die Party",
    "von tidal spiel die Musik von Rammstein",
]

# Every reply that means "I did something to the playback rather than starting
# something you named".
_TRANSPORT_CMDS = [["pause", "1"], ["pause", "0"],
                   ["mixer", "volume", "+5"], ["mixer", "volume", "-5"],
                   ["playlist", "index", "+1"], ["playlist", "index", "-1"]]


@pytest.mark.parametrize("phrase", _MUST_PLAY)
def test_a_named_request_is_never_answered_with_a_transport_command(
        lms, transport, make_tidal, phrase):
    from router import Router
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc", "name": "Egal"}]},
    )
    Router(lms).handle(phrase, source="tidal", lang="de")
    stolen = [c for c in transport.commands() if c in _TRANSPORT_CMDS]
    assert stolen == [], f"{phrase!r} was answered with {stolen}"
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()


def test_a_station_shaped_title_is_a_known_limit_not_a_transport_command():
    """«spiel Radio Ga Ga» asks the favorites for a station called "Ga Ga"
    instead of playing the Queen song — the radio step runs at 0b and claims
    it. Recorded rather than fixed: Italian and English have the identical
    shape («metti Radio Ga Ga», "play radio Ga Ga"), so it is a cross-language
    limit of that step and not something German introduced. It is out of the
    corpus above because it cannot assert playback; it is in this file so the
    absence is deliberate and not an oversight."""
    from lang import PACKS
    assert PACKS["de"].PATTERNS["radio"].search("spiel Radio Ga Ga")
    assert PACKS["it"].PATTERNS["radio"].search("metti radio Ga Ga")


def test_no_device_command_can_reach_the_play_step(lms, transport, make_tidal):
    """A command aimed at the music itself must never start music.

    Every phrase here says what to DO with the playback — on, off, louder,
    on again — and none of them names a thing to play. The library is stocked
    with a track called «Das Radio» on purpose: if any of these reaches the
    play step it will find it, and the assertion is what that costs.
    """
    from router import Router
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://42.flc",
                      "name": "Das Radio"}]},
    )
    started = []
    for phrase in _device_commands():
        before = len(transport.commands())
        Router(lms).handle(phrase, source="tidal", lang="de")
        if ["playlist", "play", "tidal://42.flc"] in transport.commands()[before:]:
            started.append(phrase)
    assert started == [], f"{len(started)} started music, e.g. {started[:5]}"


@pytest.mark.parametrize(
    "phrase, expected_cmd",
    [("starte das Radio wieder an", ["pause", "0"]),
     ("leg das Radio wieder an", ["pause", "0"]),
     ("mach das Radio auf", ["pause", "0"]),           # southern «on»
     ("spiel das Radio bitte aus", ["pause", "1"]),
     # ``abspielen``, split: it starts music, it does not stop it.
     ("spiel die Musik ab", ["pause", "0"]),
     ("spiele die Musik ab", ["pause", "0"]),
     ("mach das Radio endlich wieder aus", ["pause", "1"]),
     ("spiel das Radio leiser", ["mixer", "volume", "-5"]),
     ("starte die Musik lauter", ["mixer", "volume", "+5"])],
)
def test_the_device_verbs_all_reach_the_same_place(lms, transport, phrase,
                                                   expected_cmd):
    """The four that leaked, plus the two-adverb form the fixed-width window
    in ``pause`` could not reach."""
    from router import Router
    Router(lms).handle(phrase, lang="de")
    assert transport.last_call()[1] == expected_cmd


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
