"""The connectors belong to one language each — asserted from every side.

``engine/connectors/`` was one shared pile until French arrived: «de» is how
French names an artist and also two letters that begin a great many names, and
``parse_song_query`` takes the LAST connector, so «la canzone di Marinella di
De André» went looking for a singer called «André». French got a module and
the other three stayed in the pile, which meant «von» still split an Italian
request. Now nothing is shared, and a table is only worth being per-language
if it is actually per-language — so each of these asserts both halves: it
splits here, and it does not split anywhere else.

The price of that is the mixed request — an English phrasing heard by a
recogniser set to Italian — and it is pinned below too, so it is a decision
rather than a surprise.
"""

import pytest

from actions import parse_song_query
from connectors import CONNECTORS, for_lang
from lang import PACKS
from messages import DEFAULT_LANG

LANGS = ("it", "en", "de", "fr")


# -- the registry --------------------------------------------------------------
def test_every_language_pack_has_connectors():
    """A pack without a connector module would silently parse its requests
    with Italian's words, which is exactly the bug this package ended. The
    registries are discovered separately, so only a test can hold them level."""
    assert set(CONNECTORS) == set(PACKS)


def test_an_unknown_language_falls_back_to_the_default():
    # The same fallback ``messages.set_lang`` makes, so the words a request is
    # split with and the words it is answered in agree about "unknown".
    assert for_lang("es") is CONNECTORS[DEFAULT_LANG]


# -- the artist connectors -----------------------------------------------------
# Each row: the phrasing, and the ONE language it names an artist in.
@pytest.mark.parametrize("phrase, owner", [
    ("Comfortably Numb dei Pink Floyd", "it"),
    ("Comfortably Numb di Pink Floyd", "it"),
    ("Comfortably Numb by Pink Floyd", "en"),
    ("Comfortably Numb von Pink Floyd", "de"),
    ("Comfortably Numb de Pink Floyd", "fr"),
    ("Comfortably Numb par Pink Floyd", "fr"),
])
def test_an_artist_connector_splits_only_in_its_own_language(phrase, owner):
    assert parse_song_query(phrase, lang=owner) == {
        "title": "Comfortably Numb", "artist": "Pink Floyd", "album": None}
    for other in (lang for lang in LANGS if lang != owner):
        assert parse_song_query(phrase, lang=other) == {
            "title": phrase, "artist": None, "album": None}, other


# -- the album connectors ------------------------------------------------------
@pytest.mark.parametrize("phrase, owner", [
    ("Time dall'album Dark Side", "it"),
    ("Time dal disco Dark Side", "it"),
    ("Time from the album Dark Side", "en"),
    ("Time aus dem Album Dark Side", "de"),
    ("Time vom Album Dark Side", "de"),
    ("Time de l'album Dark Side", "fr"),
])
def test_an_album_connector_splits_only_in_its_own_language(phrase, owner):
    assert parse_song_query(phrase, lang=owner)["album"] == "Dark Side"
    for other in (lang for lang in LANGS if lang != owner):
        assert parse_song_query(phrase, lang=other)["album"] is None, other


# -- the lead fillers ----------------------------------------------------------
@pytest.mark.parametrize("phrase, owner", [
    ("la canzone Time", "it"),
    ("il brano Time", "it"),
    ("the song Time", "en"),
    ("das Lied Time", "de"),
    ("den Titel Time", "de"),
    ("la chanson Time", "fr"),
    ("le morceau Time", "fr"),
])
def test_a_lead_filler_is_stripped_only_in_its_own_language(phrase, owner):
    assert parse_song_query(phrase, lang=owner)["title"] == "Time"
    for other in (lang for lang in LANGS if lang != owner):
        assert parse_song_query(phrase, lang=other)["title"] == phrase, other


# -- what isolation costs ------------------------------------------------------
def test_a_phrase_in_the_wrong_language_stays_one_title():
    """The trade this package makes, written down.

    A request phrased in one language and heard by a recogniser set to another
    is no longer split into title and artist — «von» under Italian is a word
    in a title now. The search still runs on the full text, so the request is
    answered; only the ranking loses the hint. ``Router.handle`` sets the
    language from the mic before anything parses, which is why the case is
    rare enough to pay for «de» not breaking Italian.
    """
    q = parse_song_query("Comfortably Numb von Pink Floyd", lang="it")
    assert q["title"] == "Comfortably Numb von Pink Floyd"
    assert q["artist"] is None


# -- the tails no language calls an artist -------------------------------------
# Each language keeps its own ``NOT_AN_ARTIST``, and «me» has to sit in two of
# them: it is Italian's pronoun and the second half of «Stand By Me». The
# split walks right to left, so this is the bare title — with an artist after
# it («Stand By Me by Ben E. King», tests/test_matching.py) the last connector
# wins and the guard never fires.
@pytest.mark.parametrize("title, lang", [
    ("Ti amo di più", "it"),
    ("Stand By Me", "en"),
    ("Ein Teil von mir", "de"),
    ("Le Temps de Vivre", "fr"),
])
def test_a_connector_before_a_pronoun_is_not_an_artist(title, lang):
    assert parse_song_query(title, lang=lang) == {
        "title": title, "artist": None, "album": None}

