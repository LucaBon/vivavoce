"""French support: FR router patterns, FR replies, FR parsing separators.

Mirrors tests/test_english.py with lang="fr", plus the batteries French needs
and the other three do not: the accent a recogniser may or may not write, the
two apostrophe glyphs, the control word that sits on either side of the object
(«monte le son» / «mets la musique plus fort»), the politeness tail that lands
after it, and the play verbs that are also the words a question about the
music is asked with («qu'est-ce qui passe»).
"""

import pytest

import actions
import messages
from lang import PACKS
from messages import msg, set_lang
from router import Router


@pytest.fixture
def router(lms):
    return Router(lms)


# -- catalog ----------------------------------------------------------------
def test_catalogs_have_identical_keys():
    assert set(messages.IT) == set(messages.FR)


def test_msg_lang_selection():
    assert msg("paused", lang="fr") == "En pause."
    assert msg("paused", lang="it") == "In pausa."
    set_lang("fr")
    assert msg("paused") == "En pause."
    set_lang("it")
    assert msg("paused") == "In pausa."


# -- parsing (actions) --------------------------------------------------------
def test_parse_song_query_french_de_and_album():
    set_lang("fr")
    q = actions.parse_song_query("Comfortably Numb de Pink Floyd")
    assert q == {"title": "Comfortably Numb", "artist": "Pink Floyd", "album": None}
    q = actions.parse_song_query("Time de l'album The Dark Side of the Moon")
    assert q["title"] == "Time"
    assert q["album"] == "The Dark Side of the Moon"
    q = actions.parse_song_query("Ne me quitte pas par Jacques Brel")
    assert q["artist"] == "Jacques Brel"


def test_de_a_pronoun_is_not_an_artist():
    # «Le Temps de Vivre» is a title; there is no singer called "vivre".
    # Without the guard the split searches for one and drags every score down.
    set_lang("fr")
    q = actions.parse_song_query("Le Temps de Vivre")
    assert q["artist"] is None
    assert q["title"] == "Le Temps de Vivre"


def test_french_lead_filler_is_stripped():
    set_lang("fr")
    assert actions.parse_song_query("la chanson Time")["title"] == "Time"
    assert actions.parse_song_query("le morceau Time")["title"] == "Time"


def test_the_french_connectors_stay_out_of_italian():
    """The reason ``engine/connectors/`` exists.

    «de» is French's artist connector and two letters that begin a great many
    names. Shared with every language it broke Italian outright, because the
    split takes the LAST connector: «di Marinella di De André» went looking
    for a singer called «André». Asserted from both sides, since a per-language
    table is only worth having if it is actually per-language.
    """
    set_lang("it")
    assert actions.parse_song_query("la canzone di Marinella di De André") == {
        "title": "Marinella", "artist": "De André", "album": None}
    assert actions.parse_song_query("Comfortably Numb de Pink Floyd")["artist"] is None
    set_lang("fr")
    assert actions.parse_song_query("Comfortably Numb de Pink Floyd")["artist"] == "Pink Floyd"


# -- transport & info ---------------------------------------------------------
@pytest.mark.parametrize(
    "phrase, expected_cmd",
    [
        ("pause", ["pause", "1"]),
        ("stop", ["pause", "1"]),
        ("arrête la musique", ["pause", "1"]),
        ("coupe le son", ["pause", "1"]),
        ("éteins la radio", ["pause", "1"]),
        ("mets la musique en pause", ["pause", "1"]),
        ("reprends", ["pause", "0"]),
        ("mets la musique", ["pause", "0"]),
        ("allume la radio", ["pause", "0"]),
        ("morceau suivant", ["playlist", "index", "+1"]),
        ("suivant", ["playlist", "index", "+1"]),
        ("passe à la suivante", ["playlist", "index", "+1"]),
        ("morceau précédent", ["playlist", "index", "-1"]),
        ("en arrière", ["playlist", "index", "-1"]),
        ("monte le son", ["mixer", "volume", "+5"]),
        ("monte un peu le son", ["mixer", "volume", "+5"]),
        ("augmente le volume", ["mixer", "volume", "+5"]),
        ("mets la musique plus fort", ["mixer", "volume", "+5"]),
        ("plus fort", ["mixer", "volume", "+5"]),
        ("baisse le son", ["mixer", "volume", "-5"]),
        ("diminue le volume", ["mixer", "volume", "-5"]),
        ("mets la musique moins fort", ["mixer", "volume", "-5"]),
        ("moins fort", ["mixer", "volume", "-5"]),
    ],
)
def test_transport_phrases_fr(router, transport, phrase, expected_cmd):
    router.handle(phrase, lang="fr")
    assert transport.last_call()[1] == expected_cmd


def test_transport_replies_are_french(router, transport):
    assert router.handle("pause", lang="fr") == "En pause."
    assert router.handle("reprends", lang="fr") == "Je reprends la lecture."


@pytest.mark.parametrize("phrase", [
    "qu'est-ce qui passe",
    "qu’est-ce qui passe",
    "c'est quoi cette chanson",
    "qui chante",
    "ça joue quoi",
    "qu'est-ce qu'on écoute",
])
def test_now_playing_variants_fr(router, transport, phrase):
    """Every one of these carries a play verb. Unanchored, ``is_play`` went
    true and gated off the very step that answers the question."""
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": "PF"}]}
    assert router.handle(phrase, lang="fr") == "En ce moment : Time de PF."


# -- the accent a recogniser may or may not write -----------------------------
#
# The router matches the RAW text and ``re.I`` folds case but not accents, so
# an unaccented spelling is a silent miss — and the text box produces one every
# time. Each pair below is one phrase written the two ways it arrives.
@pytest.mark.parametrize("accented, plain, expected_cmd", [
    ("arrête la musique", "arrete la musique", ["pause", "1"]),
    ("éteins la radio", "eteins la radio", ["pause", "1"]),
    ("morceau précédent", "morceau precedent", ["playlist", "index", "-1"]),
    ("démarre la musique", "demarre la musique", ["pause", "0"]),
])
def test_a_command_routes_with_or_without_its_accents(
        router, transport, accented, plain, expected_cmd):
    for phrase in (accented, plain):
        router.handle(phrase, lang="fr")
        assert transport.last_call()[1] == expected_cmd, phrase


def test_acc_accepts_every_spelling_of_the_same_word():
    from lang.words_fr import acc
    import re
    pattern = re.compile(acc("précédent") + "$", re.I)
    for spelling in ("précédent", "precedent", "PRÉCÉDENT", "prècèdent"):
        assert pattern.match(spelling), spelling
    # And the ligature, which NFKD leaves whole.
    assert re.match(acc("cœur") + "$", "coeur", re.I)


def test_the_negated_stop_does_not_stop(router, transport):
    """The French imperative and its negation are the same word, which is not
    true in Italian («ferma» does not match "fermare"). Known limit, recorded
    rather than fixed: «arrête pas», with the «ne» dropped, still stops."""
    router.handle("n'arrête pas la musique", lang="fr")
    assert ["pause", "1"] not in transport.commands()
    router.handle("n’arrête pas la musique", lang="fr")
    assert ["pause", "1"] not in transport.commands()


# -- the two apostrophe glyphs -------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "mets l'album The Wall",
    "mets l’album The Wall",
    "mets l' album The Wall",
])
def test_both_apostrophes_reach_the_album_step(router, transport, make_tidal, phrase):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": "The Wall", "hasitems": 1}]},
    )
    speech = router.handle(phrase, source="tidal", lang="fr")
    assert speech == "Je mets l'album The Wall sur TIDAL."


# -- the politeness tail -------------------------------------------------------
#
# French puts it AFTER the object, so it hits every $-anchored pattern and
# rides along inside every greedy capture. This is de.py's «bitte» problem
# with a longer tail and a much higher frequency.
def test_a_politeness_tail_is_not_part_of_the_title(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = router.handle("mets Time s'il te plaît", source="tidal", lang="fr")
    assert speech.startswith("Je mets Time")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_a_politeness_tail_does_not_become_a_station(router, transport):
    """«mets la radio s'il te plaît» asked LMS for a station called "s'il te
    plaît" and answered that it found none — de.py's «mach das Radio bitte
    aus», one language over. It is a resume."""
    router.handle("mets la radio s'il te plaît", lang="fr")
    assert transport.last_call()[1] == ["pause", "0"]


def test_a_politeness_tail_does_not_break_a_pick(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    router.handle("quelles sont les meilleures chansons de Pink Floyd",
                  source="tidal", lang="fr")
    speech = router.handle("mets la deuxième stp", source="tidal", lang="fr")
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands(), speech


# -- the split control (French's separable verb) -------------------------------
def test_son_behind_an_article_is_the_volume_bare_it_is_a_possessive(
        router, transport, make_tidal):
    """«monte le son» is a volume command; «mets son dernier album» is a
    request to play. German has no equivalent of this one — «son» is both the
    device noun and the possessive, so it only counts behind an article."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc", "name": "Peu importe"}]},
    )
    router.handle("mets son dernier album", source="tidal", lang="fr")
    assert ["mixer", "volume", "+5"] not in transport.commands()
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()


def test_naming_what_it_is_gets_past_the_resume_shortcut(
        router, transport, make_tidal):
    """«mets la radio» is ▶ and «mets l'album Radio» is a request — the escape
    hatch de.py leaves for the same trade."""
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": "Radio", "hasitems": 1}]},
    )
    speech = router.handle("mets l'album Radio", source="tidal", lang="fr")
    assert speech == "Je mets l'album Radio sur TIDAL."


# -- the sleep timer -----------------------------------------------------------
@pytest.mark.parametrize("phrase, minutes", [
    ("arrête dans 30 minutes", 30),
    ("éteins dans trente minutes", 30),
    ("arrête dans une heure", 60),
    ("arrête dans deux heures", 120),
    ("arrête dans une demi-heure", 30),
    ("arrête dans quinze minutes", 15),
    # The vigesimal number, hyphenated and spaced: every other pack's minute
    # pattern stops at the first hyphen, and _parse_minutes tries them first.
    ("arrête dans quatre-vingt-dix minutes", 90),
    ("arrête dans quatre vingt dix minutes", 90),
])
def test_sleep_timer_fr(router, transport, phrase, minutes):
    speech = router.handle(phrase, lang="fr")
    assert speech == f"D'accord, j'arrête dans {minutes} minutes."


def test_sleep_cancel_fr(router, transport):
    router.handle("arrête dans 30 minutes", lang="fr")
    assert router.handle("annule la minuterie", lang="fr") == "Minuterie annulée."


# -- playback + French replies -------------------------------------------------
def test_play_song_fr_reply(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = router.handle("mets Time", source="tidal", lang="fr")
    assert speech.startswith("Je mets Time")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_play_song_not_found_fr(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"}, items={"S": []})
    speech = router.handle("mets Xyzzy", source="tidal", lang="fr")
    assert speech == "Je n'ai trouvé aucun morceau pour Xyzzy."
    assert getattr(speech, "ok", None) is False


def test_play_album_fr(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": "The Wall", "hasitems": 1}]},
    )
    speech = router.handle("mets l'album The Wall", source="tidal", lang="fr")
    assert speech == "Je mets l'album The Wall sur TIDAL."


@pytest.mark.parametrize("phrase", [
    "mets Time",
    "met Time",
    "joue Time",
    "lance Time",
    "passe-moi Time",
    "écoute Time",
    "je veux écouter Time",
    "démarre Time",
])
def test_generic_play_variants_fr(router, transport, make_tidal, phrase):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    router.handle(phrase, source="tidal", lang="fr")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands(), phrase


def test_play_title_containing_transport_word_fr(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://5.flc",
                      "name": "Arrête de me mentir"}]},
    )
    router.handle("mets Arrête de me mentir", source="tidal", lang="fr")
    assert ["playlist", "play", "tidal://5.flc"] in transport.commands()
    assert ["pause", "1"] not in transport.commands()


def test_qobuz_misheard_by_asr_fr(router, transport, make_tidal):
    # fr-FR Web Speech writes "qobuz" as "cobusse"; the sound-alikes were
    # already in parsing.py before French had a pack.
    transport.responses["qobuz"] = make_tidal(
        categories={"Tracks": "T"},
        items={"T": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    speech = router.handle("sur cobusse mets Time", source="local", lang="fr")
    assert speech.startswith("Je mets Time")
    assert ["playlist", "play", "qobuz://9.flac"] in transport.commands()


def test_local_prefix_fr(router, transport):
    transport.responses["search"] = {}
    speech = router.handle("de ma musique mets Xyzzy", lang="fr")
    assert speech == "Je n'ai pas trouvé Xyzzy dans ta musique."


def test_fallback_fr(router, transport):
    speech = router.handle("quel temps fera-t-il demain", lang="fr")
    assert speech.startswith("Je n'ai pas compris.")


def test_handle_many_empty_fr(router):
    out = router.handle_many([], lang="fr")
    assert out["speech"] == "Je n'ai rien entendu."


# -- moods ---------------------------------------------------------------------
def test_a_vague_request_reaches_the_mood_table(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Genres": "G"},
        items={"G": [{"id": "g1", "name": "Jazz", "hasitems": 1}],
               "g1": [{"isaudio": 1, "url": "tidal://3.flc", "name": "So What"}]},
    )
    speech = router.handle("mets de la musique douce", source="tidal", lang="fr")
    assert speech, "a mood phrase must be answered"


def test_stopping_a_mood_is_not_starting_one(router, transport):
    """The anchor, which is it.py's first condition: «arrête la musique
    triste» carries a marker noun and a mood word and asks to STOP."""
    router.handle("arrête la musique triste", lang="fr")
    assert transport.last_call()[1] == ["pause", "1"]


# -- queue ---------------------------------------------------------------------
def test_queue_clear_fr(router, transport):
    assert router.handle("vide la file d'attente", lang="fr") == "File d'attente vidée."
    assert router.handle("vide la file d’attente", lang="fr") == "File d'attente vidée."


# -- numbered list flow --------------------------------------------------------
def test_top_tracks_then_choose_number_fr(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    speech = router.handle("quelles sont les meilleures chansons de Pink Floyd",
                           source="tidal", lang="fr")
    assert speech.startswith("Voici les morceaux les plus écoutés de Pink Floyd.")
    assert "1 : Time" in speech and "2 : Money" in speech
    speech = router.handle("mets le numéro deux", source="tidal", lang="fr")
    assert speech == "Je mets Money sur TIDAL."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


@pytest.mark.parametrize("pick", [
    "mets le numéro 2", "mets la deuxième", "mets la deuxieme",
    "mets la seconde", "mets la deuxième chanson", "la 2",
])
def test_choose_ordinal_fr(router, transport, make_tidal, pick):
    """Both spellings of every accented ordinal: ``_as_number`` lowercases its
    token and does not fold it, so «deuxième» and «deuxieme» are two keys."""
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    router.handle("quelles sont les meilleures chansons de Pink Floyd",
                  source="tidal", lang="fr")
    router.handle(pick, source="tidal", lang="fr")
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands(), pick


def test_choose_without_list_fr(router, transport):
    speech = router.handle("mets le numéro deux", lang="fr")
    assert speech.startswith("Demande-moi d'abord une liste")


# -- the pick phrase the web client sends back ---------------------------------
def test_the_web_clients_pick_phrase_is_one_the_router_parses(
        router, transport, make_tidal):
    """``static/js/chat.js`` renders the numbered list as buttons and sends a
    phrase back. It is the one place the JS is not data-driven, so the phrase
    it writes has to be a phrase this pack reads."""
    import re
    chat = open("localvoice/static/js/chat.js", encoding="utf-8").read()
    phrase = re.search(r'fr: \(n\) => "([^"]+)" \+ n', chat).group(1)
    assert PACKS["fr"].PATTERNS["choose_number"].search(phrase + "2")


# -- language isolation --------------------------------------------------------
def test_italian_still_default(router, transport):
    assert router.handle("pausa") == "In pausa."


def test_languages_do_not_leak_between_requests(router, transport):
    assert router.handle("pause", lang="fr") == "En pause."
    assert router.handle("pausa", lang="it") == "In pausa."
    assert router.handle("pause", lang="en") == "Paused."
    assert router.handle("pause", lang="de") == "Pausiert."


# -- the invariant, asserted by construction -----------------------------------
#
# German's version of this exists because five review rounds found the same
# shape: a guard was widened and the step that catches what it declines was
# not, so a phrase fell past every catcher to the play step and started a
# stream. French's product has a different axis set, because the word that
# decides what happens can sit on either side of the object — «monte le son»
# in front, «mets la musique plus fort» behind.

# Every verb in _V_ON ∪ _V_OFF ∪ _V_UP ∪ _V_DOWN — and, just as importantly,
# every verb in _PLAY, which is the set the ``radio`` guard declines on. The
# first version of this list held only the catchers' verbs, and so asserted
# nothing about the twelve the guard knew and they did not: «passe la
# musique», «écoute la musique» and «fais jouer la radio» all fell past every
# catcher and started a stream, with the cross product green.
_DEV_VERBS = ["mets", "met", "remets", "allume", "lance", "démarre",
              "coupe", "arrête", "arrete", "éteins", "stoppe",
              "monte", "augmente", "baisse", "diminue", "réduis",
              "joue", "jouer", "jouez", "lancer", "lancez", "relance",
              "écoute", "écouter", "ecoute", "balance", "passe",
              "fais jouer", "je veux écouter", "j'aimerais écouter"]
# «son» and «volume» are missing from the article-free row on purpose: bare,
# «son» is the possessive, and «mets son dernier album» is a request to play.
_DEV_FREE_NOUNS = ["musique", "radio", "zique"]
_DEV_HELD_NOUNS = ["son", "volume"]
_DEV_ARTICLES = ["la ", "le ", "l'", "l’", "du "]
_DEV_TAILS = ["", " s'il te plaît", " s'il vous plaît", " stp", " svp",
              " un peu", " maintenant", " plus fort", " moins fort",
              " en pause", " un peu plus fort"]


def _device_commands():
    for verb in _DEV_VERBS:
        for tail in _DEV_TAILS:
            for noun in _DEV_FREE_NOUNS:
                yield f"{verb} {noun}{tail}"
                for article in _DEV_ARTICLES:
                    yield f"{verb} {article}{noun}{tail}"
            for noun in _DEV_HELD_NOUNS:
                for article in _DEV_ARTICLES:
                    yield f"{verb} {article}{noun}{tail}"


# The other direction, which the cross product cannot see: a request that
# NAMES something must never be answered with a transport command. Both halves
# are needed and neither implies the other — German's one-directional version
# shipped for one commit and, alone, required «spiel die Musik ab» to mean
# stop.
_MUST_PLAY = [
    "mets la chanson Coupe le son",       # a title that IS a device command
    "mets le titre Monte le son",
    "mets Plus Fort de Nolwenn Leroy",    # the «plus» trap
    "mets son dernier album",             # «son» the possessive
    "joue son premier disque",
    "mets Radiohead",                     # «radio» must not match inside a word
    "mets du Pink Floyd",                 # the partitive with no marker noun
    "mets de la musique de Céline Dion",
    "mets Time s'il te plaît",            # the politeness tail
    "mets Time s’il te plaît",            # …and the same tail with U+2019
    "sur tidal mets la musique de Téléphone",
    "mets Le Son de la Rue",
]

# Every reply that means "I did something to the playback rather than starting
# something you named".
_TRANSPORT_CMDS = [["pause", "1"], ["pause", "0"],
                   ["mixer", "volume", "+5"], ["mixer", "volume", "-5"],
                   ["playlist", "index", "+1"], ["playlist", "index", "-1"]]


@pytest.mark.parametrize("phrase", _MUST_PLAY)
def test_a_named_request_is_never_answered_with_a_transport_command(
        lms, transport, make_tidal, phrase):
    # Both categories — see tests/test_german.py for why: «sur tidal mets la
    # musique de Téléphone» names an artist and now walks the Artists chain
    # instead of being downgraded to a song search.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S", "Artists": "A"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc", "name": "Peu importe"}],
               "A": [{"type": "outline", "id": "AR", "name": "Téléphone"}],
               "AR": [{"name": "Top Tracks", "id": "TT"}],
               "TT": [{"isaudio": 1, "url": "tidal://7.flc", "name": "Peu importe"}]},
    )
    Router(lms).handle(phrase, source="tidal", lang="fr")
    stolen = [c for c in transport.commands() if c in _TRANSPORT_CMDS]
    assert stolen == [], f"{phrase!r} was answered with {stolen}"
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()


def test_no_device_command_can_reach_the_play_step(lms, transport, make_tidal):
    """A command aimed at the music itself must never start music.

    Every phrase here says what to DO with the playback and none of them names
    a thing to play. The library is stocked with «La Radio» on purpose: if any
    of them reaches the play step it will find it, and the assertion is what
    that costs.
    """
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://42.flc", "name": "La Radio"}]},
    )
    started = []
    for phrase in _device_commands():
        before = len(transport.commands())
        Router(lms).handle(phrase, source="tidal", lang="fr")
        if ["playlist", "play", "tidal://42.flc"] in transport.commands()[before:]:
            started.append(phrase)
    assert started == [], f"{len(started)} started music, e.g. {started[:8]}"


@pytest.mark.parametrize("phrase, expected_cmd", [
    ("coupe la musique plus fort", ["pause", "1"]),   # the contradictory tail
    ("mets la musique plus fort", ["mixer", "volume", "+5"]),
    ("mets le son moins fort", ["mixer", "volume", "-5"]),
    ("allume la radio s'il te plaît", ["pause", "0"]),
    ("éteins la zique maintenant", ["pause", "1"]),
    ("monte un peu le son stp", ["mixer", "volume", "+5"]),
    ("baisse la musique svp", ["mixer", "volume", "-5"]),
    ("remets la musique", ["pause", "0"]),
])
def test_the_device_verbs_all_reach_the_same_place(lms, transport, phrase,
                                                   expected_cmd):
    Router(lms).handle(phrase, lang="fr")
    assert transport.last_call()[1] == expected_cmd


def test_a_station_shaped_title_is_a_known_limit_not_a_transport_command():
    """«mets la radio Nostalgie» asks the favorites for a station rather than
    playing the band — the radio step runs ahead of the play steps and claims
    it. Recorded rather than fixed: Italian, English and German have the
    identical shape, so it is a limit of that step and not something French
    introduced. It is out of the corpus above because it cannot assert
    playback; it is here so the absence is deliberate and not an oversight."""
    assert PACKS["fr"].PATTERNS["radio"].search("mets la radio Nostalgie")
    assert PACKS["it"].PATTERNS["radio"].search("metti radio Ga Ga")


def test_every_verb_the_radio_guard_declines_is_caught_by_a_later_step():
    """The guard and its catchers have to read one list.

    ``radio`` declines «mets la radio» and friends with a lookahead built from
    ``_PLAY``; the steps that must then catch the phrase — resume, vol_up,
    vol_down — are built from ``_V_ON``. While those were two lists, the
    twelve verbs in the first and not the second fell past every catcher to
    the play step: «passe la musique» searched the library for a record called
    "la musique" and found one. ``_V_ON`` is ``_PLAY`` plus «allume» now, and
    this asserts the containment directly rather than through the phrases the
    cross product happens to enumerate.
    """
    import re
    from lang import words_fr as w
    v_on = re.compile(w._V_ON + r"$", re.I)
    for verb in ("mets", "met", "remets", "joue", "jouer", "jouez", "lance",
                 "lancer", "relance", "démarre", "balance", "fais jouer",
                 "écoute", "écouter", "je veux écouter", "passe", "allume"):
        assert v_on.match(verb), f"{verb!r} sets is_play but no DEV() step catches it"


@pytest.mark.parametrize("phrase, expected_cmd", [
    # One row per verb the guard knows. Each of these started a stream.
    ("passe la radio", ["pause", "0"]),
    ("passe la musique", ["pause", "0"]),
    ("écoute la musique", ["pause", "0"]),
    ("balance la musique", ["pause", "0"]),
    ("fais jouer la radio", ["pause", "0"]),
    ("je veux écouter la musique", ["pause", "0"]),
    ("passe la musique plus fort", ["mixer", "volume", "+5"]),
])
def test_a_play_verb_aimed_at_the_device_is_still_a_device_command(
        lms, transport, phrase, expected_cmd):
    Router(lms).handle(phrase, lang="fr")
    assert transport.last_call()[1] == expected_cmd


@pytest.mark.parametrize("phrase", [
    "ajoute Time à la file d'attente",
    "ajoute Time dans la file d'attente",
    "mets Time à la file d'attente",
    "rajoute Time à la liste d'attente",
])
def test_adding_to_the_queue_is_not_reading_it_out(
        lms, transport, make_tidal, phrase):
    """``queue_list`` ran two steps earlier with the bare noun «file
    d'attente» as one of its alternatives, so it matched inside every add
    request and answered by reading the queue. Every sibling pack requires a
    listing marker — «coda di riproduzione», «warteschlange anzeigen»,
    "queue list" — and French now does too."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = Router(lms).handle(phrase, source="tidal", lang="fr")
    assert "ajouté" in speech, speech


def test_the_queue_can_still_be_read_out(lms, transport):
    assert Router(lms).handle("montre-moi la file d'attente", lang="fr") == (
        "La file d'attente est vide.")
    assert Router(lms).handle("c'est quoi la file d'attente", lang="fr") == (
        "La file d'attente est vide.")


@pytest.mark.parametrize("phrase", [
    "passe la suivante", "passe cette chanson", "passe celle-là",
    "passe à la suivante", "passe au suivant",
])
def test_passe_is_a_skip_in_every_shape_that_names_no_title(
        lms, transport, phrase):
    """«passe» is a play verb and half of two things that are not. Guarded on
    «à/au/aux» alone, «passe la suivante» set is_play — which gates the whole
    transport block off — and reached the library instead."""
    Router(lms).handle(phrase, lang="fr")
    assert transport.last_call()[1] == ["playlist", "index", "+1"], phrase


def test_passe_moi_is_still_a_play(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    Router(lms).handle("passe-moi Time", source="tidal", lang="fr")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


@pytest.mark.parametrize("phrase", [
    "n'arrête pas la musique",
    "n’arrête pas la musique",
    "ne coupe pas la musique",
    # The two the fixed-width lookbehind alone could not see: a clitic between
    # «ne» and the verb, and the dropped «ne» — which is the ordinary spoken
    # form, and therefore the one that matters most in a voice app.
    "ne l'arrête pas",
    "arrête pas la musique",
    "coupe pas la musique",
    "éteins pas la musique",
])
def test_a_negated_stop_does_not_stop(lms, transport, phrase):
    Router(lms).handle(phrase, lang="fr")
    assert ["pause", "1"] not in transport.commands(), phrase


@pytest.mark.parametrize("phrase", [
    "qu'est-ce qui passe", "qu’est-ce qui passe", "ça joue quoi",
    "j'écoute quoi", "j'écoute quoi là", "on écoute quoi",
    "qu'est-ce qu'on écoute", "c'est quoi cette chanson", "qui chante",
    "c'est quel morceau", "quel est ce titre",
])
def test_every_way_of_asking_what_is_playing(lms, transport, phrase):
    """Anchoring is_play made these harmless; it did not make them answered.
    «j'écoute quoi» fell through to the fallback message until nowplaying
    learned the shape its own module docstring cites."""
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": "PF"}]}
    assert Router(lms).handle(phrase, lang="fr") == "En ce moment : Time de PF.", phrase


@pytest.mark.parametrize("phrase", [
    "et mets la chanson Stop",
    "alors mets l'album Stop",
    "bon, mets Stop",
    "dis-moi, mets Stop",
])
def test_a_discourse_particle_in_front_does_not_turn_a_play_into_a_pause(
        lms, transport, make_tidal, phrase):
    """The anchored is_play was documented as costing «alors, mets Time» —
    harmless, because it falls back. The cost was understated: the transport
    steps are unanchored searches, so with is_play false «et mets la chanson
    Stop» did not fall back, it paused. A closed lead-in list rather than "any
    two words", because the words this must not admit are «ça», «on» and
    «qui» — the whole reason is_play is anchored."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://8.flc", "name": "Stop"}]},
    )
    Router(lms).handle(phrase, source="tidal", lang="fr")
    assert ["pause", "1"] not in transport.commands(), phrase


def test_a_lead_in_does_not_reopen_the_question_hole(lms, transport):
    """The lead-in list is closed for a reason — «ça» and «on» must never be
    read as one, or asking what is playing switches off the ability to ask."""
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": "PF"}]}
    assert Router(lms).handle("alors ça joue quoi", lang="fr") == (
        "En ce moment : Time de PF.")


def test_a_control_word_is_not_part_of_a_station_name(lms, transport):
    """«mets la radio Nostalgie plus fort» asked for a station called
    "Nostalgie plus fort". The station is «Nostalgie»; the volume request is
    dropped, because the radio step runs ahead of vol_up — the step order's
    limit, and a smaller one than a station nobody has."""
    speech = Router(lms).handle("mets la radio Nostalgie plus fort", lang="fr")
    assert "Nostalgie" in speech and "plus fort" not in speech, speech


def test_en_boucle_is_phrasing_and_not_part_of_the_title(
        lms, transport, make_tidal):
    """There is no repeat mode, so «en boucle» is a word this router acts on
    exactly as much as it acts on «maintenant». The pack used to carry a
    generic_play_suffix for it, which generic_play won every time — dead code
    for a job _ADV does properly."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = Router(lms).handle("mets Time en boucle", source="tidal", lang="fr")
    assert speech.startswith("Je mets Time")


@pytest.mark.parametrize(
    "phrase",
    ["mets la musique de Pink Floyd",
     "mets les chansons de Pink Floyd",
     "mets toutes les chansons de Pink Floyd",
     "mets quelque chose de Pink Floyd",
     "mets l'artiste Pink Floyd",
     # The partitive, which is the ORDINARY way to ask in French — «les
     # chansons de X» is the marked one. Missing from the list, these fell
     # through to the generic branch, where the whole phrase is read as a
     # title: nothing matches it, and a service that trusts its own ranking
     # played a stranger's song. It is how «mets des chansons de Teddy Swims»
     # came back as one track by somebody else.
     "mets des chansons de Pink Floyd",
     "mets des morceaux de Pink Floyd",
     "mets quelques chansons de Pink Floyd",
     "joue des titres de Pink Floyd",
     # ...and the partitive introducing the noun itself.
     "mets de la musique de Pink Floyd"],
)
def test_artist_variants_fr(lms, transport, make_tidal, phrase):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"}]},
    )
    reply = Router(lms).handle(phrase, source="tidal", lang="fr")
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands(), reply


@pytest.mark.parametrize("phrase", [
    "mets la chanson de Prévert",      # a Gainsbourg title, not an artist
    "mets Le Temps des Cerises",
    "mets de la musique douce",        # a mood, and it must stay one
])
def test_a_title_or_a_mood_is_not_an_artist_request_fr(phrase):
    from router import PATTERNS
    assert not PATTERNS["fr"]["artist"].search(phrase), phrase
