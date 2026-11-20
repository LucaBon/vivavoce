# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""How a name *sounds*, written down so that two spellings can be compared.

A speech recogniser writes what it hears in the spelling of the language it
was told to expect. Asked for Italian, it hears «Kamin» and writes «camin»:
the right sound in the only spelling Italian has for it, since Italian barely
uses the letter k. A streaming service's search compares letters, so «camin»
never finds «Kamin». Comparing the two by sound does.

:func:`phonetic_key` reduces a name to a rough pronunciation in capital
letters — «camin» and «Kamin» both become ``KAMIN``, «Johnny», «Jony» and
«Gioni» all become ``JONI`` — and :func:`phonetic_score` compares two names
by whichever is closer, their letters or their sound.

The rules are the spelling conventions of the *request's* language, applied
to both sides. That is the right reading for the recogniser's half, which is
written in exactly that convention; for the catalogue's half (a Russian name
in Latin letters, say) it is an approximation, and a good one where it
matters: the letters a foreign name is spelt with and the letters an Italian
recogniser writes for its sound converge under the same rules.

This is a key for *ranking candidates*, never for deciding on its own. Close
keys are not the same name — «Emin» and «Eminem» score 0.8 — and the caller
weighs a phonetic match against what the ordinary search found (see
docs/name-recognition-design.md, §1.3).

Hand-written and stdlib-only, like the rest of the server: no metaphone
package, and none of the published algorithms is Italian-aware anyway.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

# One rule: a regex on the folded, lower-case text, and its replacement. The
# replacement may use capitals, which mark a sound already decided — no later
# lower-case rule can touch it. Order matters inside a language: longer
# spellings first («sch» before «sc», «ci» + vowel before «c»).
#
# The few capital sound marks used:
#   K  the hard c/k/q sound        J  the "j" of "John", Italian «gi», «ge»
#   C  the "ch" of "church", Italian «ci», «ce»
#   X  the "sh" of "shoe", Italian «sci», French «ch», German «sch»
_Rule = Tuple["re.Pattern[str]", str]


def _rules(*pairs: Tuple[str, str]) -> List[_Rule]:
    return [(re.compile(pattern), repl) for pattern, repl in pairs]


_COMMON_TAIL = _rules(
    ("ph", "f"), ("th", "t"), ("ck", "K"), ("x", "KS"),
    ("q", "K"), ("k", "K"), ("w", "v"), ("y", "i"), ("h", ""),
)

_RULES: Dict[str, List[_Rule]] = {
    "it": _rules(
        ("sch", "SK"), ("sc(?=[ei])", "X"), ("sci(?=[aou])", "X"),
        # «gh» is a hard g, decided here: left lower case, the «g» + e/i
        # rule below would turn «ghiro» into «jiro».
        ("ch", "K"), ("gh", "G"), ("gli", "li"), ("gn", "ni"),
        ("ci(?=[aou])", "C"), ("c(?=[ei])", "C"),
        ("gi(?=[aou])", "J"), ("g(?=[ei])", "J"),
        # «qu» and «cu» + vowel are one sound in Italian («quadro», «cuoco»),
        # and a recogniser writes either for a foreign «Quin».
        ("qu", "Ku"), ("c", "K"), ("j", "J"),
    ),
    "en": _rules(
        ("sch", "SK"), ("sh", "X"), ("tch", "C"), ("ch", "C"),
        ("ee", "i"), ("ea", "i"), ("oo", "u"),
        ("c(?=[eiy])", "s"), ("c", "K"), ("j", "J"), ("dg(?=[eiy])", "J"),
    ),
    "de": _rules(
        ("sch", "X"), ("ch", "K"), ("ei", "ai"), ("ie", "i"),
        ("eu", "oi"), ("tz", "ts"), ("z", "ts"), ("v", "f"), ("w", "v"),
        ("c", "K"), ("j", "i"),
    ),
    "fr": _rules(
        ("eau", "o"), ("au", "o"), ("ou", "u"), ("oi", "ua"),
        ("ch", "X"), ("qu", "K"), ("gu(?=[ei])", "g"),
        ("c(?=[eiy])", "s"), ("c", "K"), ("g(?=[ei])", "X"), ("j", "X"),
        # Final consonants French does not say: «Debussy» keeps its s, but
        # «Thomas» does not, and «Renaud» is «reno».
        (r"(?<=[aeiou])[stdx]\b", ""),
    ),
    "es": _rules(
        ("ll", "i"), ("ch", "C"), ("qu", "K"), ("c(?=[ei])", "s"),
        ("z", "s"), ("c", "K"), ("j", "H"), ("g(?=[ei])", "H"), ("v", "b"),
    ),
}

_FOLD = {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d"}
_NOT_A_LETTER = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")
_DOUBLES = re.compile(r"(.)\1+")


def fold(text: Optional[str]) -> str:
    """Lower case, no accents, letters/digits/single spaces only.

    «EMIN & JONY» → ``emin jony``; «Björk» → ``bjork``. The ampersand goes:
    nobody says it, and the recogniser writes «e» or «and» in its place —
    which stays, since it is a word somebody did say.
    """
    lowered = "".join(_FOLD.get(c, c) for c in (text or "").lower())
    plain = "".join(c for c in unicodedata.normalize("NFKD", lowered)
                    if not unicodedata.combining(c))
    return _SPACES.sub(" ", _NOT_A_LETTER.sub(" ", plain)).strip()


def phonetic_key(text: Optional[str], lang: str = "it") -> str:
    """A name as it sounds, in capitals, words kept apart by single spaces.

    ``lang`` is the language the request was made in; an unknown one falls
    back to Italian, like the rest of the engine.
    """
    rules = _RULES.get(lang, _RULES["it"]) + _COMMON_TAIL
    words = []
    for word in fold(text).split(" "):
        for pattern, repl in rules:
            word = pattern.sub(repl, word)
        word = _DOUBLES.sub(r"\1", word.upper())
        if word:
            words.append(word)
    return " ".join(words)


def phonetic_score(a: Optional[str], b: Optional[str], lang: str = "it") -> float:
    """How alike two names are, 0..1: by letters or by sound, whichever is
    closer.

    The maximum rather than an average on purpose: two names spelt the same
    are a full match however their sounds compare, and a spelling the
    recogniser invented should not be held against a name that sounds
    exactly like it.
    """
    fa, fb = fold(a), fold(b)
    if not fa or not fb:
        return 0.0
    letters = difflib.SequenceMatcher(None, fa, fb).ratio()
    ka, kb = phonetic_key(a, lang), phonetic_key(b, lang)
    sound = difflib.SequenceMatcher(None, ka, kb).ratio() if ka and kb else 0.0
    return max(letters, sound)
