"""The phonetic key (localvoice/pro/phonetic.py): which spellings collide.

The cases come from real transcriptions (docs/name-recognition-design.md §0):
an Italian recogniser writes «camin» for «Kamin» and «johnny» for «JONY».
The key exists to make those meet, and must not make different names meet:
the second half of this file matters as much as the first.
"""

import pytest

from pro.phonetic import fold, phonetic_key, phonetic_score


# -- what an Italian recogniser writes, and the name it meant ------------------

@pytest.mark.parametrize("heard, meant", [
    ("camin", "Kamin"),        # Italian has no k: the same sound, spelt with c
    ("kiara", "Chiara"),
    ("gioni", "Jony"),         # «gi» + vowel is the "j" of John
    ("johnny", "Jony"),
    ("pink floid", "Pink Floyd"),
    ("bjork", "Björk"),        # accents are not sounds
    ("cuin", "Quin"),
    ("filip", "Philip"),
])
def test_an_italian_spelling_of_the_same_sound_has_the_same_key(heard, meant):
    assert phonetic_key(heard, "it") == phonetic_key(meant, "it")
    assert phonetic_score(heard, meant, "it") == 1.0


def test_the_cases_that_started_this():
    assert phonetic_key("camin") == "KAMIN" == phonetic_key("Kamin")
    assert phonetic_key("EMIN & JONY") == "EMIN JONI"


@pytest.mark.parametrize("a, b", [
    ("Metallica", "Megadeth"),
    ("Vasco Rossi", "The Beatles"),
    ("Queen", "David Bowie"),
    ("Mina", "Muse"),
])
def test_different_names_stay_apart(a, b):
    assert phonetic_score(a, b, "it") < 0.5


def test_close_is_not_the_same():
    """«Emin» and «Eminem» are near by sound and are two artists. The score
    says "near", and that is all it may say: deciding is the caller's job,
    against what the ordinary search found. If this number ever reaches 1.0
    the key has started merging names, and «metti Eminem» is at risk."""
    assert 0.5 < phonetic_score("emin", "Eminem", "it") < 0.9


# -- the Italian sounds the rules are written for ------------------------------

@pytest.mark.parametrize("word, key", [
    ("chiesa", "KIESA"),      # ch before e/i is hard
    ("ciao", "CAO"),          # ci + vowel is the "ch" of church, no i
    ("cena", "CENA"),
    ("gelato", "JELATO"),
    ("giallo", "JALO"),       # and doubles collapse
    ("ghiro", "GIRO"),
    ("scena", "XENA"),        # sc before e/i is "sh"
    ("scuola", "SKUOLA"),
    ("gnocchi", "NIOKI"),
    ("quadro", "KUADRO"),     # qu and cu + vowel: one sound
    ("hotel", "OTEL"),        # h is silent
])
def test_italian_spelling_rules(word, key):
    assert phonetic_key(word, "it") == key


@pytest.mark.parametrize("lang, word, key", [
    ("en", "Shakira", "XAKIRA"),
    ("en", "Cecilia", "SESILIA"),   # English c before e/i is s, not Italian ch
    ("de", "Schubert", "XUBERT"),
    ("de", "Wagner", "VAGNER"),
    ("fr", "Renaud", "RENO"),
    ("fr", "Chopin", "XOPIN"),
    ("es", "José", "HOSE"),
])
def test_each_language_reads_with_its_own_rules(lang, word, key):
    assert phonetic_key(word, lang) == key


def test_an_unknown_language_reads_as_italian():
    assert phonetic_key("camin", "xx") == phonetic_key("camin", "it")


# -- folding and the edges -----------------------------------------------------

def test_fold_keeps_words_and_drops_symbols():
    assert fold("EMIN & JONY") == "emin jony"
    assert fold("  AC/DC  ") == "ac dc"
    assert fold("Sigur Rós") == "sigur ros"
    assert fold("Straße") == "strasse"


@pytest.mark.parametrize("a, b", [("", "Kamin"), ("Kamin", None), ("&", "!")])
def test_nothing_to_compare_scores_zero(a, b):
    assert phonetic_score(a, b) == 0.0
    assert phonetic_key(a) == "" or phonetic_key(b) == ""


def test_the_same_letters_are_a_full_match_whatever_the_sound():
    """The maximum of letters and sound, not the average: a name compared
    with itself must never come out short."""
    for name in ("Kamin", "Shakira", "Måneskin", "Sigur Rós"):
        assert phonetic_score(name, name, "it") == 1.0
