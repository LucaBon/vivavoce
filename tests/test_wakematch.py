"""``engine/wakematch.py``: the wake phrase in a line of text.

The rules are a port of ``static/js/wakeword.js``, so most of these cases are
the browser's own regressions restated in Python — if this file and that file
ever disagree, a household gets one behaviour on the phone and another on the
box. The split/glued cases are the ones the browser cannot do at all, and
come straight off the bench: Vosk wrote 13 of 15 real utterances as
``vivavoce`` and 2 as ``viva voce``.
"""

import pytest

from wakematch import (command_after_wake, contains_wake, normalize,
                       token_matches, tokens)

WAKE = "vivavoce"


# --- the plain cases --------------------------------------------------------

def test_one_breath_returns_the_command():
    assert command_after_wake("vivavoce metti i Pink Floyd", WAKE) == \
        "metti i Pink Floyd"


def test_phrase_alone_returns_empty_not_none():
    # Empty string and None mean different things: "" arms the two-step flow
    # ("yes? tell me the command"), None means nobody said anything to us.
    assert command_after_wake("vivavoce", WAKE) == ""


def test_absent_phrase_returns_none():
    assert command_after_wake("metti i Pink Floyd", WAKE) is None


def test_empty_phrase_never_matches():
    # A blank wake-word field must not turn every noise into a command.
    assert command_after_wake("qualunque cosa", "") is None
    assert command_after_wake("qualunque cosa", "   ") is None


def test_phrase_in_the_middle_of_a_sentence():
    assert command_after_wake("aspetta un attimo, vivavoce metti Time",
                              WAKE) == "metti Time"


def test_case_and_accents_are_ignored_when_matching():
    assert command_after_wake("VIVAVOCE pausa", WAKE) == "pausa"
    assert contains_wake("perché vivavoce", WAKE) is True


def test_the_command_keeps_its_original_spelling():
    # The tail is about to be sent as a command: flattening its accents would
    # hand the catalogue a title it cannot find.
    assert command_after_wake("vivavoce metti Anouar Brahem", WAKE) == \
        "metti Anouar Brahem"
    assert command_after_wake("vivavoce metti Perché no", WAKE) == \
        "metti Perché no"


# --- the mis-hearings it must forgive ---------------------------------------

def test_one_edit_is_forgiven():
    assert command_after_wake("vivavoci pausa", WAKE) == "pausa"


def test_split_into_two_words_still_fires():
    # 2 of 15 real utterances. Token-for-token a one-word phrase can never
    # match two words, so these were lost entirely before.
    assert command_after_wake("viva voce metti Time", WAKE) == "metti Time"


def test_split_phrase_heard_glued_still_fires():
    # The same rule in the other direction, for a two-word phrase.
    assert command_after_wake("ciaoimpianto pausa", "ciao impianto") == "pausa"


def test_two_word_phrase_matches_word_for_word():
    assert command_after_wake("ciao impianto metti i Pink Floyd",
                              "ciao impianto") == "metti i Pink Floyd"


# --- the false triggers it must refuse --------------------------------------

@pytest.mark.parametrize("heard", [
    "viva",              # the browser's own regression: a shared 4-char head
    "viva la vita",      # a confusable from make_wake_corpus.py
    "vivace",
    "provo la voce",
    "prova la voce",
    "vieni via",
    "voce",
])
def test_near_misses_do_not_fire(heard):
    assert command_after_wake(heard, WAKE) is None


def test_the_phrase_glued_to_more_words_does_not_fire():
    # "vivavoce" is a prefix of "vivavoceancora", but a prefix that covers
    # barely half the token is a different word, not a mis-hearing.
    assert command_after_wake("vivavocedavvero pausa", WAKE) is None


def test_a_long_run_is_not_glued_into_a_match():
    # Guard on the split rule: gluing enough words together will eventually
    # contain the phrase, and that must not count.
    assert command_after_wake("viva voce ancora", WAKE) == "ancora"
    assert command_after_wake("la viva della voce", WAKE) is None


def test_a_glued_run_has_to_be_spelled_exactly():
    # Measured on the 120 near-miss clips from make_wake_corpus.py
    # --confusables: "la vita e voce" came back from the recogniser as
    # "la vita voce", and "vitavoce" is exactly one edit from "vivavoce".
    # Forgiving a moved space AND a wrong letter is two tolerances spent on
    # one mistake, which is precisely where a near-miss gets through.
    assert command_after_wake("la vita e voce", WAKE) is None
    assert command_after_wake("la vita voce", WAKE) is None
    # The real split is untouched: glued, it IS the word.
    assert command_after_wake("viva voce pausa", WAKE) == "pausa"


def test_an_unsplit_word_still_gets_its_edit():
    # The tightening applies only when the word count changed. One heard word
    # against a one-word phrase is the ordinary comparison, edit and all.
    assert command_after_wake("vivavoci pausa", WAKE) == "pausa"


# --- the pieces -------------------------------------------------------------

def test_normalize_strips_accents_and_case():
    assert normalize("Perché È Così") == "perche e cosi"
    assert normalize(None) == ""


def test_tokens_drops_empties():
    assert tokens("  due   parole  ") == ["due", "parole"]
    assert tokens("") == []


@pytest.mark.parametrize("a,b,expected", [
    ("vivavoce", "vivavoce", True),
    ("vivavoci", "vivavoce", True),     # one edit
    ("vivavoc", "vivavoce", True),      # one deletion
    ("viva", "vivavoce", False),        # 50% coverage: a different word
    ("vivavocee", "vivavoce", True),    # one insertion
    ("pausa", "vivavoce", False),
])
def test_token_matches(a, b, expected):
    assert token_matches(a, b) is expected
    assert token_matches(b, a) is expected  # symmetric


def test_contains_wake_agrees_with_command_after_wake():
    for text in ("vivavoce", "vivavoce pausa", "viva voce pausa", "niente"):
        assert contains_wake(text, WAKE) is \
            (command_after_wake(text, WAKE) is not None)
