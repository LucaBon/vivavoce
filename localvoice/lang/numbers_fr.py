"""French spoken numbers and durations — the tables ``fr.py`` exposes. See
``numbers_it.py`` for why they live beside the patterns rather than in them,
and ``numbers_de.py`` for why an accented word is written twice: ``_as_number``
lowercases its token but does not fold it, so "deuxième" and "deuxieme" are two
different keys, and only one of them is what the recogniser wrote.
"""

from __future__ import annotations

from .base import c

# One to ten carry no accent — the one gift French gives this file.
NUM_WORDS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}

# Both spellings on every accented entry, plus the digit-and-suffix forms a
# recogniser writes when it decides the word was a number after all.
ORDINAL_WORDS = {
    "premier": 1, "première": 1, "premiere": 1, "1er": 1, "1ere": 1,
    # «seconde» is also a unit of time and «second» an ordinary adjective.
    # Both stay: the pick step is gated on an open list, so an ordinal can
    # only be read as one while there is something to pick from.
    "deuxième": 2, "deuxieme": 2, "second": 2, "seconde": 2, "2eme": 2,
    "troisième": 3, "troisieme": 3, "3eme": 3,
    "quatrième": 4, "quatrieme": 4,
    "cinquième": 5, "cinquieme": 5,
    "sixième": 6, "sixieme": 6,
    "septième": 7, "septieme": 7,
    "huitième": 8, "huitieme": 8,
    "neuvième": 9, "neuvieme": 9,
    "dixième": 10, "dixieme": 10,
}

MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
    # Seventy, eighty and ninety twice each, because the lookup is a raw
    # ``.lower()`` on whatever the recogniser wrote and French counts these in
    # scores: they are hyphenated on paper and spaced by half the engines.
    # They reach the table intact only because the minute pattern below admits
    # both — the Italian, English and German ones all stop at the hyphen, and
    # ``_parse_minutes`` tries every pack in turn.
    "soixante-dix": 70, "soixante dix": 70,
    "quatre-vingts": 80, "quatre-vingt": 80, "quatre vingts": 80,
    "quatre vingt": 80,
    "quatre-vingt-dix": 90, "quatre vingt dix": 90,
})

# A spoken number as one token: hyphens and inner spaces both, because
# «quatre-vingt-dix» is one number written three ways. Lazy, so the literal
# that follows it in each pattern is what bounds it rather than the class.
_NUMTOK = r"[a-zà-öø-ÿœæ]+(?:[\s\-][a-zà-öø-ÿœæ]+)*?"

# The tail of a sleep command («arrête dans <tail>»), most specific first.
DURATIONS = (
    (c(r"^une\s+demi[\s\-]?heure\b"), 30),
    (c(r"^(?:une|un|1)\W?\s*heure\b"), 60),
    (c(rf"^(\d+|{_NUMTOK})\s*heures\b"), "hours"),
    (c(rf"^(\d+|{_NUMTOK})\s*(?:minut\w*|min\b)"), "minutes"),
)
