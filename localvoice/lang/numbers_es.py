"""Spanish spoken numbers and durations — the tables ``es.py`` exposes. See
``numbers_it.py`` for why they live beside the patterns rather than in them,
and ``numbers_fr.py`` for why an accented word is written twice here and
nowhere else in the pack: ``_as_number`` lowercases its token but does not
fold it, so "décima" and "decima" are two different keys, and only one of them
is what the recogniser wrote. :func:`~lang.words_es.acc` cannot help — these
are dict keys, not patterns.
"""

from __future__ import annotations

from .base import c

# One to ten carry no accent. "un" and "una" are both here because the article
# and the numeral are the same word: «pon la una» is a pick, not a time.
NUM_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

# Both genders on every entry — the pick is «la primera» for a canción and «el
# primero» for a tema, and people say both — and both spellings on the three
# that carry an accent.
ORDINAL_WORDS = {
    "primero": 1, "primera": 1, "primer": 1, "1o": 1, "1a": 1,
    "segundo": 2, "segunda": 2, "2o": 2, "2a": 2,
    "tercero": 3, "tercera": 3, "tercer": 3, "3o": 3, "3a": 3,
    "cuarto": 4, "cuarta": 4,
    "quinto": 5, "quinta": 5,
    "sexto": 6, "sexta": 6,
    "séptimo": 7, "septimo": 7, "séptima": 7, "septima": 7,
    "octavo": 8, "octava": 8,
    "noveno": 9, "novena": 9,
    "décimo": 10, "decimo": 10, "décima": 10, "decima": 10,
}

MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "noventa": 90,
    # Spanish welds the twenties into one word and spaces every ten above
    # them, so «veinticinco» is one token and «treinta y cinco» is three. The
    # minute pattern below admits both shapes; these are the compounds anyone
    # actually sets a timer with.
    "veinticinco": 25, "treinta y cinco": 35, "cuarenta y cinco": 45,
})

# A spoken number as one token, or as the «treinta y cinco» compound Spanish
# writes with spaces. Lazy, so the literal that follows it in each pattern is
# what bounds it rather than the class.
_NUMTOK = r"[a-záéíóúüñ]+(?:\s+y\s+[a-záéíóúüñ]+)?"

# The tail of a sleep command («apaga en <tail>»), most specific first — and
# «una hora y media» is why "most specific" is not decoration: read in the
# other order, `^una\s*hora` matches its first two words and silently drops
# the half.
DURATIONS = (
    (c(r"^media\s+hora\b"), 30),
    (c(r"^(?:una\s+|1\s*)?hora\s+y\s+media\b"), 90),
    (c(r"^(?:una|1)\s*hora\b"), 60),
    (c(rf"^(\d+|{_NUMTOK})\s*horas\b"), "hours"),
    (c(rf"^(\d+|{_NUMTOK})\s*(?:minut\w*|min\b)"), "minutes"),
)
