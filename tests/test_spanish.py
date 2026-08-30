"""Spanish support: ES router patterns, ES replies, ES parsing separators.

Mirrors tests/test_english.py with lang="es", plus the batteries Spanish needs
and the other four do not: the preposition that is also the stop verb («música
PARA dormir» against «para la música»), the pronoun welded onto the imperative
(«ponme», «súbelo», «quítala»), the inverted question mark a recogniser puts in
front of a question, and the article that is the whole difference between «pon
música» and «pon la música».
"""

import re

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
    assert set(messages.IT) == set(messages.ES)


def test_msg_lang_selection():
    assert msg("paused", lang="es") == "En pausa."
    assert msg("paused", lang="it") == "In pausa."
    set_lang("es")
    assert msg("paused") == "En pausa."
    set_lang("it")
    assert msg("paused") == "In pausa."


def test_the_offer_buttons_are_answers_this_pack_parses():
    """``offer_yes``/``offer_no`` are the words the web app sends when a
    button under a yes/no offer is tapped, so they have to be phrases the
    pack's own ``yes``/``no`` patterns read. Tapping is typing."""
    P = PACKS["es"].PATTERNS
    assert P["yes"].match(messages.ES["offer_yes"])
    assert P["no"].match(messages.ES["offer_no"])


# -- parsing (actions) --------------------------------------------------------
def test_parse_song_query_spanish_de_and_album():
    set_lang("es")
    q = actions.parse_song_query("Comfortably Numb de Pink Floyd")
    assert q == {"title": "Comfortably Numb", "artist": "Pink Floyd", "album": None}
    q = actions.parse_song_query("Time del álbum The Dark Side of the Moon")
    assert q["title"] == "Time"
    assert q["album"] == "The Dark Side of the Moon"


def test_de_a_pronoun_is_not_an_artist():
    # «La Chica de Ayer» is a record; there is no singer called «ayer». Without
    # the guard the split searches for one and drags every score down.
    set_lang("es")
    q = actions.parse_song_query("La Chica de Ayer")
    assert q["artist"] is None
    assert q["title"] == "La Chica de Ayer"


def test_the_longest_connector_wins():
    """«de los» has to be tried before «de», or the artist step is handed
    "los Planetas" as a name. connectors/it.py records the same for «dell'»."""
    set_lang("es")
    q = actions.parse_song_query("Himno de los Planetas")
    assert q["artist"] == "Planetas"


def test_spanish_lead_filler_is_stripped():
    set_lang("es")
    assert actions.parse_song_query("la canción Time")["title"] == "Time"
    assert actions.parse_song_query("el tema Time")["title"] == "Time"


def test_de_belongs_to_two_languages_and_to_no_others():
    """French claimed «de» first and Spanish claims it too, which is fine and
    was the whole point of taking the shared pile apart: a request is split
    with the table of the language it was heard in. Italian must still be
    untouched by it — that is the bug ``engine/connectors/`` exists for."""
    for code in ("es", "fr"):
        assert actions.parse_song_query(
            "Comfortably Numb de Pink Floyd", lang=code)["artist"] == "Pink Floyd"
    for code in ("it", "en", "de"):
        assert actions.parse_song_query(
            "Comfortably Numb de Pink Floyd", lang=code)["artist"] is None
    assert actions.parse_song_query(
        "la canzone di Marinella di De André", lang="it") == {
            "title": "Marinella", "artist": "De André", "album": None}


# -- transport & info ---------------------------------------------------------
@pytest.mark.parametrize(
    "phrase, expected_cmd",
    [
        ("pausa", ["pause", "1"]),
        ("stop", ["pause", "1"]),
        ("para la música", ["pause", "1"]),
        ("quita la música", ["pause", "1"]),
        ("apaga la radio", ["pause", "1"]),
        ("corta la música", ["pause", "1"]),
        ("pon la música en pausa", ["pause", "1"]),
        ("sigue", ["pause", "0"]),
        ("pon la música", ["pause", "0"]),
        ("enciende la radio", ["pause", "0"]),
        ("tema siguiente", ["playlist", "index", "+1"]),
        ("siguiente", ["playlist", "index", "+1"]),
        ("pasa a la siguiente", ["playlist", "index", "+1"]),
        ("tema anterior", ["playlist", "index", "-1"]),
        ("vuelve atrás", ["playlist", "index", "-1"]),
        ("vuelve a la anterior", ["playlist", "index", "-1"]),
        ("sube el volumen", ["mixer", "volume", "+5"]),
        ("sube un poco el volumen", ["mixer", "volume", "+5"]),
        ("aumenta el volumen", ["mixer", "volume", "+5"]),
        ("pon la música más alta", ["mixer", "volume", "+5"]),
        ("más alto", ["mixer", "volume", "+5"]),
        ("baja el volumen", ["mixer", "volume", "-5"]),
        ("disminuye el volumen", ["mixer", "volume", "-5"]),
        ("pon la música más baja", ["mixer", "volume", "-5"]),
        ("más bajo", ["mixer", "volume", "-5"]),
    ],
)
def test_transport_phrases_es(router, transport, phrase, expected_cmd):
    router.handle(phrase, lang="es")
    assert transport.last_call()[1] == expected_cmd


def test_transport_replies_are_spanish(router, transport):
    assert router.handle("pausa", lang="es") == "En pausa."
    assert router.handle("sigue", lang="es") == "Sigo con la reproducción."


@pytest.mark.parametrize("phrase", [
    "qué suena",
    "¿qué suena?",
    "que suena",
    "qué canción es esta",
    "quién canta",
    "qué está sonando",
    "qué estamos escuchando",
])
def test_now_playing_variants_es(router, transport, phrase):
    """Every one of these has to survive both the missing accent and the
    inverted mark, and none of them may set ``is_play`` — which gates off the
    very step that answers the question."""
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": "PF"}]}
    assert router.handle(phrase, lang="es") == "Está sonando Time de PF."


# -- «para»: the stop verb that is also the commonest preposition -------------
#
# The Spanish decision of the pack. `pause` is gated only on ¬is_play, so an
# unanchored `\bpara\b` paused the hi-fi on any bare phrase carrying the word —
# and half the mood vocabulary carries it.


@pytest.mark.parametrize("phrase", [
    "para la música",
    "para la radio",
    "párala",
    "para",
])
def test_para_aimed_at_the_device_is_a_stop(router, transport, phrase):
    router.handle(phrase, lang="es")
    assert transport.last_call()[1] == ["pause", "1"], phrase


@pytest.mark.parametrize("phrase", [
    "música para dormir",
    "algo para cenar",
    "canciones para estudiar",
    "Para Todos los Públicos",
    "para siempre",
])
def test_para_as_a_preposition_never_stops_the_music(router, transport, phrase):
    """None of these is a request to stop. The first three are moods, the
    fourth is a record and the fifth is neither — what they share is the word,
    and before DEV() owned it they all paused."""
    router.handle(phrase, lang="es")
    assert ["pause", "1"] not in transport.commands(), phrase


def test_the_negated_stop_is_a_different_word(router, transport):
    """French needed a lookbehind here, because its imperative and its
    negation are the same word. Spanish negates with the subjunctive — «no
    pares» is not «para» — so ``\\b`` does the work for free, and this is what
    asserts the claim words_es.py makes."""
    P = PACKS["es"].PATTERNS
    assert not P["pause"].search("no pares la música")
    assert not P["pause"].search("no quites la música")
    assert not P["pause"].search("no apagues la música")


# -- the pronoun welded onto the verb -----------------------------------------
@pytest.mark.parametrize("phrase, expected_cmd", [
    ("quítala", ["pause", "1"]),
    ("apágala", ["pause", "1"]),
    ("pon la música", ["pause", "0"]),
    ("ponme la música", ["pause", "0"]),
    ("súbeme el volumen", ["mixer", "volume", "+5"]),
    ("bájame el volumen", ["mixer", "volume", "-5"]),
])
def test_the_clitic_rides_along_with_the_verb(router, transport, phrase,
                                              expected_cmd):
    router.handle(phrase, lang="es")
    assert transport.last_call()[1] == expected_cmd, phrase


def test_the_accent_shift_is_free():
    """«sube» becomes «súbelo»: the stress mark appears only once the clitic
    is there. ``acc()`` spells the stem as "every vowel may carry an accent",
    so the shifted form is the stem plus ``_CL`` and not a second entry — the
    claim words_es.py makes about why no verb here is written twice."""
    from lang.words_es import _CL, acc
    stem = re.compile(acc("sube") + _CL + r"$", re.I)
    for form in ("sube", "súbe", "súbelo", "súbeme", "súbemelo", "subelo"):
        assert stem.match(form), form


# -- the accent a recogniser may or may not write ------------------------------
@pytest.mark.parametrize("accented, plain, expected_cmd", [
    ("párala", "parala", ["pause", "1"]),
    ("pon la música", "pon la musica", ["pause", "0"]),
    ("qué canción es esta", "que cancion es esta", None),
])
def test_a_command_routes_with_or_without_its_accents(
        router, transport, accented, plain, expected_cmd):
    """The router matches the RAW text and ``re.I`` folds case but not
    accents, so «musica» typed into the box is not «música» to a regex.
    ``acc()`` is that fact encoded once."""
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": "PF"}]}
    first = router.handle(accented, lang="es")
    second = router.handle(plain, lang="es")
    assert str(first) == str(second), (accented, plain)
    if expected_cmd:
        assert transport.last_call()[1] == expected_cmd


# -- the inverted marks --------------------------------------------------------
@pytest.mark.parametrize("phrase, plain", [
    ("¿qué hay en la cola?", "qué hay en la cola"),
    ("¡pon Time!", "pon Time"),
    ("¿sí?", "sí"),
])
def test_the_inverted_marks_never_reach_a_pattern(phrase, plain):
    """Spanish opens a question with «¿», and the trailing strip in
    parsing.py takes the «?» while leaving the «¿» welded to the first word —
    where it breaks every ^-anchored pattern at once. Stripped in
    clean_command rather than written into eleven patterns."""
    from parsing import clean_command
    assert clean_command(phrase) == plain


# -- the politeness tail -------------------------------------------------------
#
# It lands AFTER the object in Spanish, as it does in French, so it hits every
# $-anchored pattern and rides along inside every greedy capture.


def test_a_politeness_tail_is_not_part_of_the_title(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = router.handle("pon Time por favor", source="tidal", lang="es")
    assert speech.startswith("Pongo Time")


def test_a_politeness_tail_does_not_become_a_station(router, transport):
    """«pon la radio por favor» asked LMS for a station called "por favor"
    and reported that it found none — de.py's «mach das Radio bitte aus» with
    a Spanish tail. It is ▶, and the radio guard is what makes it one."""
    router.handle("pon la radio por favor", lang="es")
    assert transport.last_call()[1] == ["pause", "0"]


def test_a_politeness_tail_does_not_break_a_pick(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    router.handle("cuáles son los mejores temas de Pink Floyd",
                  source="tidal", lang="es")
    router.handle("pon la segunda por favor", source="tidal", lang="es")
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


# -- the article that separates asking from pressing play ----------------------
def test_the_article_is_the_whole_difference(router, transport, make_tidal):
    """«pon música» is the ordinary way to ask for something to listen to;
    «pon la música» is ▶. French lets «mets musique» resume; DEV() here
    requires the article, so the first falls to the play steps instead."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://8.flc", "name": "Música"}]},
    )
    router.handle("pon la música", source="tidal", lang="es")
    assert transport.last_call()[1] == ["pause", "0"]
    router.handle("pon música", source="tidal", lang="es")
    assert transport.last_call()[1] != ["pause", "0"]


# -- the sleep timer -----------------------------------------------------------
@pytest.mark.parametrize("phrase, minutes", [
    ("apaga en 30 minutos", 30),
    ("apaga dentro de 30 minutos", 30),
    ("para dentro de treinta minutos", 30),
    ("apaga en una hora", 60),
    ("apaga en dos horas", 120),
    ("apaga en media hora", 30),
    ("apaga en quince minutos", 15),
    # The compound Spanish writes with spaces, which every other pack's
    # minute pattern stops at the first word of.
    ("apaga en treinta y cinco minutos", 35),
    # «una hora y media» read in the wrong order matches its first two words
    # and silently drops the half.
    ("apaga en una hora y media", 90),
])
def test_sleep_timer_es(router, transport, phrase, minutes):
    speech = router.handle(phrase, lang="es")
    assert speech == f"Vale, apago dentro de {minutes} minutos."


def test_sleep_cancel_es(router, transport):
    router.handle("apaga en 30 minutos", lang="es")
    assert router.handle("cancela el temporizador",
                         lang="es") == "Temporizador cancelado."


def test_a_title_carrying_en_is_not_a_timer(router, transport, make_tidal):
    """The captured tail has to parse as a duration, or the phrase falls
    through — which is what keeps «pon Nada en la Nevera» a play."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://4.flc",
                      "name": "Nada en la Nevera"}]},
    )
    router.handle("pon Nada en la Nevera", source="tidal", lang="es")
    assert ["playlist", "play", "tidal://4.flc"] in transport.commands()


# -- playback + Spanish replies ------------------------------------------------
def test_play_song_es_reply(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    speech = router.handle("pon Time", source="tidal", lang="es")
    assert speech.startswith("Pongo Time")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_play_song_not_found_es(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"},
                                              items={"S": []})
    speech = router.handle("pon Xyzzy", source="tidal", lang="es")
    assert speech == "No he encontrado ningún tema de Xyzzy."
    assert getattr(speech, "ok", None) is False


def test_play_album_es(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "A"},
        items={"A": [{"id": "alb1", "name": "The Wall", "hasitems": 1}]},
    )
    speech = router.handle("pon el álbum The Wall", source="tidal", lang="es")
    assert speech == "Pongo el álbum The Wall en TIDAL."


@pytest.mark.parametrize("phrase", [
    "pon Time",
    "ponme Time",
    "pone Time",
    "poné Time",
    "coloca Time",
    "mete Time",
    "reproduce Time",
    "escucha Time",
    "quiero escuchar Time",
    "pincha Time",
])
def test_generic_play_variants_es(router, transport, make_tidal, phrase):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Time"}]},
    )
    router.handle(phrase, source="tidal", lang="es")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands(), phrase


def test_play_title_containing_transport_word_es(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://5.flc",
                      "name": "Para de Mentirme"}]},
    )
    router.handle("pon Para de Mentirme", source="tidal", lang="es")
    assert ["playlist", "play", "tidal://5.flc"] in transport.commands()
    assert ["pause", "1"] not in transport.commands()


def test_qobuz_misheard_by_asr_es(router, transport, make_tidal):
    # es-ES Web Speech writes "qobuz" as «cobús»; the sound-alikes were
    # already in parsing.py before Spanish had a pack.
    transport.responses["qobuz"] = make_tidal(
        categories={"Tracks": "T"},
        items={"T": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    speech = router.handle("en cobús pon Time", source="local", lang="es")
    assert speech.startswith("Pongo Time")
    assert ["playlist", "play", "qobuz://9.flac"] in transport.commands()


def test_local_prefix_es(router, transport):
    transport.responses["search"] = {}
    speech = router.handle("de mi música pon Xyzzy", lang="es")
    assert speech == "No he encontrado Xyzzy en tu música."


def test_fallback_es(router, transport):
    speech = router.handle("qué tiempo hará mañana", lang="es")
    assert speech.startswith("No te he entendido.")


def test_handle_many_empty_es(router):
    out = router.handle_many([], lang="es")
    assert out["speech"] == "No he oído nada."


# -- moods ---------------------------------------------------------------------
def test_a_vague_request_reaches_the_mood_table(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Genres": "G"},
        items={"G": [{"id": "g1", "name": "Jazz", "hasitems": 1}],
               "g1": [{"isaudio": 1, "url": "tidal://3.flc", "name": "So What"}]},
    )
    speech = router.handle("pon algo de jazz", source="tidal", lang="es")
    assert speech, "a mood phrase must be answered"


def test_stopping_a_mood_is_not_starting_one(router, transport):
    """The anchor, which is it.py's first condition: «quita la música triste»
    carries a marker noun and a mood word and asks to STOP."""
    router.handle("quita la música triste", lang="es")
    assert transport.last_call()[1] == ["pause", "1"]


# -- queue ---------------------------------------------------------------------
def test_queue_clear_es(router, transport):
    assert router.handle("vacía la cola", lang="es") == "Cola vaciada."
    assert router.handle("limpia la cola", lang="es") == "Cola vaciada."


@pytest.mark.parametrize("phrase", [
    "añade Time a la cola",
    "añade Time en la cola",
    "agrega Time a la cola",
])
def test_adding_to_the_queue_is_not_reading_it_out(
        lms, transport, make_tidal, phrase):
    """``queue_list`` runs two steps earlier; written with the bare noun
    «cola» as one of its alternatives it matched inside every add request and
    answered by reading the queue out. Every sibling pack requires a listing
    marker and Spanish does too."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://6.flc", "name": "Time"}]},
    )
    speech = Router(lms).handle(phrase, source="tidal", lang="es")
    assert speech.startswith("He añadido Time"), phrase


# -- numbered list flow --------------------------------------------------------
def test_top_tracks_then_choose_number_es(router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    speech = router.handle("cuáles son los mejores temas de Pink Floyd",
                           source="tidal", lang="es")
    assert speech.startswith("Estos son los temas más escuchados de Pink Floyd.")
    assert "1: Time" in speech and "2: Money" in speech
    speech = router.handle("pon el número dos", source="tidal", lang="es")
    assert speech == "Pongo Money en TIDAL."
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


@pytest.mark.parametrize("pick", [
    "pon el número 2", "pon la segunda", "pon el segundo",
    "pon la segunda canción", "la 2", "pon el número dos",
])
def test_choose_ordinal_es(router, transport, make_tidal, pick):
    """Both genders on every ordinal: the pick is «la segunda» for a canción
    and «el segundo» for a tema, and ``_as_number`` reads the token raw."""
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "Ar"},
        items={"Ar": [{"id": "a1", "name": "Pink Floyd", "hasitems": 1}],
               "a1": [{"id": "tt", "name": "Top Tracks", "hasitems": 1}],
               "tt": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                      {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}]},
    )
    router.handle("cuáles son los mejores temas de Pink Floyd",
                  source="tidal", lang="es")
    router.handle(pick, source="tidal", lang="es")
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands(), pick


def test_choose_without_list_es(router, transport):
    speech = router.handle("pon el número dos", lang="es")
    assert speech.startswith("Pídeme antes una lista")


# -- the pick phrase the web client sends back ---------------------------------
def test_the_web_clients_pick_phrase_is_one_the_router_parses():
    """``static/js/chat.js`` renders the numbered list as buttons and sends a
    phrase back. It is the one place the JS is not data-driven, so the phrase
    it writes has to be a phrase this pack reads."""
    chat = open("localvoice/static/js/chat.js", encoding="utf-8").read()
    phrase = re.search(r'es: \(n\) => "([^"]+)" \+ n', chat).group(1)
    assert PACKS["es"].PATTERNS["choose_number"].search(phrase + "2")


# -- language isolation --------------------------------------------------------
def test_italian_still_default(router, transport):
    assert router.handle("pausa") == "In pausa."


def test_languages_do_not_leak_between_requests(router, transport):
    assert router.handle("pausa", lang="es") == "En pausa."
    assert router.handle("pausa", lang="it") == "In pausa."
    assert router.handle("pause", lang="en") == "Paused."
    assert router.handle("pause", lang="de") == "Pausiert."
    assert router.handle("pause", lang="fr") == "En pause."


# -- the invariant, asserted by construction -----------------------------------
#
# German's version of this exists because five review rounds found the same
# shape: a guard was widened and the step that catches what it declines was
# not, so a phrase fell past every catcher to the play step and started a
# stream. French added the axis for a control word on either side of the
# object. Spanish's product adds the clitic, which multiplies every verb.

# Every verb in _V_ON ∪ _V_OFF ∪ _V_UP ∪ _V_DOWN — and, just as importantly,
# every verb in _PLAY, which is the set the ``radio`` guard declines on. A list
# holding only the catchers' verbs asserts nothing about the ones the guard
# knows and they do not; that is the defect words_fr.py records, and it is the
# reason _V_ON is written as _PLAY plus two rather than as a shorter second
# list.
_DEV_VERBS = ["pon", "ponme", "ponlo", "pone", "poné", "ponga", "póngame",
              "coloca", "mete", "echa", "pincha", "reproduce", "escucha",
              "toca", "quiero escuchar", "enciende", "arranca",
              "quita", "quítala", "apaga", "apágala", "corta", "detén",
              "silencia", "para", "párala",
              "sube", "súbelo", "aumenta", "baja", "bájala", "reduce"]
# Every device noun takes an article in this pack — that is the decision
# «pon música» pays for, and the cross product says so by never offering one
# without.
_DEV_NOUNS = ["música", "musica", "radio", "volumen", "sonido"]
_DEV_ARTICLES = ["la ", "el ", "los ", "del ", "de la "]
_DEV_TAILS = ["", " por favor", " porfa", " gracias", " ya", " ahora",
              " un poco", " más alto", " más bajo", " en pausa"]


def _device_commands():
    for verb in _DEV_VERBS:
        for tail in _DEV_TAILS:
            for noun in _DEV_NOUNS:
                for article in _DEV_ARTICLES:
                    yield f"{verb} {article}{noun}{tail}"


# The other direction, which the cross product cannot see: a request that
# NAMES something must never be answered with a transport command. Both halves
# are needed and neither implies the other — German's one-directional version
# shipped for one commit and, alone, required «spiel die Musik ab» to mean
# stop.
_MUST_PLAY = [
    "pon la canción Quita el Volumen",     # a title that IS a device command
    "pon el tema Sube el Volumen",
    "pon Más Fuerte de Alejandro Sanz",    # the «más» trap
    "pon Para Todos los Públicos",         # the «para» trap
    "pon El Sonido de la Calle",           # a device noun inside a title
    "pon Radiohead",                       # «radio» must not match inside a word
    "pon algo de Pink Floyd",              # the partitive with no marker noun
    "pon la música de Rosalía",
    "pon Time por favor",                  # the politeness tail
    "ponme Time",                          # the clitic
    "en tidal pon la música de Rosalía",
    "pon canciones de Pink Floyd",
]

# Every reply that means "I did something to the playback rather than starting
# something you named".
_TRANSPORT_CMDS = [["pause", "1"], ["pause", "0"],
                   ["mixer", "volume", "+5"], ["mixer", "volume", "-5"],
                   ["playlist", "index", "+1"], ["playlist", "index", "-1"]]


@pytest.mark.parametrize("phrase", _MUST_PLAY)
def test_a_named_request_is_never_answered_with_a_transport_command(
        lms, transport, make_tidal, phrase):
    # Both categories — see tests/test_german.py for why: «en tidal pon la
    # música de Rosalía» names an artist and walks the Artists chain instead
    # of being downgraded to a song search.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S", "Artists": "A"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc", "name": "Da igual"}],
               "A": [{"type": "outline", "id": "AR", "name": "Rosalía"}],
               "AR": [{"name": "Top Tracks", "id": "TT"}],
               "TT": [{"isaudio": 1, "url": "tidal://7.flc", "name": "Da igual"}]},
    )
    Router(lms).handle(phrase, source="tidal", lang="es")
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
        Router(lms).handle(phrase, source="tidal", lang="es")
        if ["playlist", "play", "tidal://42.flc"] in transport.commands()[before:]:
            started.append(phrase)
    assert started == [], f"{len(started)} started music, e.g. {started[:8]}"


@pytest.mark.parametrize("phrase, expected_cmd", [
    ("quita la música más alta", ["pause", "1"]),   # the contradictory tail
    ("pon la música más alta", ["mixer", "volume", "+5"]),
    ("pon el sonido más bajo", ["mixer", "volume", "-5"]),
    ("enciende la radio por favor", ["pause", "0"]),
    ("apaga la música ahora", ["pause", "1"]),
    ("sube un poco el volumen porfa", ["mixer", "volume", "+5"]),
    ("baja la música por favor", ["mixer", "volume", "-5"]),
    ("pon la música otra vez", ["pause", "0"]),
])
def test_the_device_verbs_all_reach_the_same_place(lms, transport, phrase,
                                                   expected_cmd):
    Router(lms).handle(phrase, lang="es")
    assert transport.last_call()[1] == expected_cmd


def test_the_service_suffix_reads_the_one_verb_list():
    """``service_suffix`` is a ``.format`` template, so fr.py writes its verbs
    out by hand — and a hand-copied second list is the defect words_de.py
    records: a verb in ``_PLAY`` and not in the copy sets is_play and then
    loses the suffix form, so «escucha Time en Qobuz» is answered by the
    DEFAULT service instead of the named one.

    This pack builds it from ``_PLAY`` instead, and the property that makes
    that legal is asserted here rather than assumed: ``_PLAY`` contains no
    brace, so it survives the ``.format`` that expands ``{s}``.
    """
    from lang import words_es as w
    assert "{" not in w._PLAY and "}" not in w._PLAY
    template = PACKS["es"].PATTERNS["service_suffix"]
    compiled = re.compile(template.format(s="qobuz"), re.I)
    for verb in ("pon", "ponme", "coloca", "mete", "echa", "pincha",
                 "reproduce", "escucha", "toca", "quiero escuchar"):
        assert compiled.search(f"{verb} Time en qobuz"), verb


@pytest.mark.parametrize("phrase", [
    "escucha Time en cobús",
    "reproduce Time en cobús",
    "ponme Time en cobús",
    "toca Time en cobús",
])
def test_a_service_named_after_the_title_reaches_that_service(
        lms, transport, make_tidal, phrase):
    """The other half of the test above, end to end: every play verb has to
    reach the named service and not the default one."""
    transport.responses["qobuz"] = make_tidal(
        categories={"Tracks": "T"},
        items={"T": [{"isaudio": 1, "url": "qobuz://9.flac", "name": "Time"}]},
    )
    Router(lms).handle(phrase, source="local", lang="es")
    assert ["playlist", "play", "qobuz://9.flac"] in transport.commands(), phrase


def test_every_verb_the_radio_guard_declines_is_caught_by_a_later_step():
    """The guard and its catchers have to read one list.

    ``radio`` declines «pon la radio» and friends with a lookahead built from
    ``_PLAY``; the steps that must then catch the phrase — resume, vol_up,
    vol_down — are built from ``_V_ON``. While those are two lists, every verb
    in the first and not the second falls past every catcher to the play step.
    ``_V_ON`` is ``_PLAY`` plus «enciende» and «arranca», and this asserts the
    containment directly rather than through the phrases the cross product
    happens to enumerate.
    """
    from lang import words_es as w
    v_on = re.compile(w._V_ON + r"$", re.I)
    for verb in ("pon", "ponme", "ponlo", "pone", "poné", "ponga", "coloca",
                 "mete", "echa", "pincha", "reproduce", "escucha", "toca",
                 "quiero escuchar", "enciende", "arranca"):
        assert v_on.match(verb), f"{verb!r} sets is_play but no DEV() step catches it"


@pytest.mark.parametrize("phrase, expected_cmd", [
    # One row per verb the guard knows.
    ("toca la radio", ["pause", "0"]),
    ("escucha la música", ["pause", "0"]),
    ("mete la música", ["pause", "0"]),
    ("reproduce la música", ["pause", "0"]),
    ("quiero escuchar la música", ["pause", "0"]),
    ("pon la música más alta", ["mixer", "volume", "+5"]),
])
def test_a_play_verb_aimed_at_the_device_is_still_a_device_command(
        lms, transport, phrase, expected_cmd):
    Router(lms).handle(phrase, lang="es")
    assert transport.last_call()[1] == expected_cmd


@pytest.mark.parametrize("title", [
    "Vuelve",                 # Ricky Martin — «vuelve» says what it goes back to
    "Volver",
    "Para Todos los Públicos",
    "La Radio",
    "El Sonido de la Calle",
    "Corta Venas",
    "Nada en la Nevera",
])
def test_a_bare_title_is_not_a_transport_command(router, transport,
                                                 make_tidal, title):
    """A title typed or picked with no play verb in front of it has no
    ``is_play`` to protect it: every ¬is_play transport step reads it raw.

    These seven survive, and three of them are why a pattern above is written
    the way it is — «vuelve» and «pasa» name what they go to, «para» lives
    only inside DEV(). What does NOT survive is recorded rather than hidden:
    «Pausa», «Anterior», «Adelante», «Salta», «Más Fuerte» and «Sigue Tu
    Camino» are read as commands, because the word IS the command and nothing
    else is in the phrase. Every sibling pack makes the identical trade —
    it.py with «pausa» and «più forte», en.py with "next", fr.py with «plus
    fort» — and the escape hatch is the same one they all have: «pon la
    canción Salta» names what it wants and reaches the play step.
    """
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://3.flc", "name": title}]},
    )
    router.handle(title, source="tidal", lang="es")
    stolen = [c for c in transport.commands() if c in _TRANSPORT_CMDS]
    assert stolen == [], f"{title!r} was answered with {stolen}"


@pytest.mark.parametrize("title", [
    "Pausa", "Anterior", "Adelante", "Salta", "Más Fuerte", "Sigue Tu Camino",
])
def test_naming_a_command_shaped_title_still_plays_it(router, transport,
                                                      make_tidal, title):
    """The other half, and the escape hatch the test above names: bare, these
    six are commands; behind a play verb they are titles, because is_play
    gates the whole transport block."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://3.flc", "name": title}]},
    )
    router.handle(f"pon la canción {title}", source="tidal", lang="es")
    assert ["playlist", "play", "tidal://3.flc"] in transport.commands(), title


def test_a_station_shaped_title_is_a_known_limit_not_a_transport_command():
    """«pon la radio Cadena SER» asks the favorites for a station rather than
    playing a band of that name — the radio step runs ahead of the play steps
    and claims it. Recorded rather than fixed: all four sibling packs have the
    identical shape, so it is a limit of that step and not something Spanish
    introduced."""
    assert PACKS["es"].PATTERNS["radio"].search("pon la radio Cadena SER")
    assert PACKS["it"].PATTERNS["radio"].search("metti radio Ga Ga")
