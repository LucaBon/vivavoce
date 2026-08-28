"""German spoken numbers and durations — the tables ``de.py`` exposes. See
``numbers_it.py`` for why they live beside the patterns rather than in them.

German is why the umlaut spellings appear twice: ``_as_number`` lowercases its
token but does not fold it, so "fünf" and "funf" are two different keys.
"""

from __future__ import annotations

from .base import c

# Web Speech transcribes a spoken position as a word ("drei"), not "3". The
# umlaut spellings are listed twice on purpose: ``_as_number`` lowercases its
# token but does not fold it, so "fünf" and "funf" are two different keys.
NUM_WORDS = {
    "eins": 1, "ein": 1, "eine": 1, "einer": 1, "zwei": 2, "drei": 3,
    "vier": 4, "fünf": 5, "funf": 5, "sechs": 6, "sieben": 7, "acht": 8,
    "neun": 9, "zehn": 10,
}

# People answer a read-out list with «die zweite» at least as often as with
# the bare number, and German inflects the ordinal for gender and case: the
# recogniser writes whichever the speaker used.
ORDINAL_WORDS = {
    "erste": 1, "erster": 1, "erstes": 1, "ersten": 1,
    "zweite": 2, "zweiter": 2, "zweites": 2, "zweiten": 2,
    "dritte": 3, "dritter": 3, "drittes": 3, "dritten": 3,
    "vierte": 4, "vierter": 4, "viertes": 4, "vierten": 4,
    "fünfte": 5, "funfte": 5, "fünfter": 5, "funfter": 5,
    "fünftes": 5, "funftes": 5, "fünften": 5, "funften": 5,
    "sechste": 6, "sechster": 6, "sechstes": 6, "sechsten": 6,
    "siebte": 7, "siebter": 7, "siebtes": 7, "siebten": 7,
    "siebente": 7, "achte": 8, "achter": 8, "achtes": 8, "achten": 8,
    "neunte": 9, "neunter": 9, "neuntes": 9, "neunten": 9,
    "zehnte": 10, "zehnter": 10, "zehntes": 10, "zehnten": 10,
}

# Durations go beyond list positions: the sleep timer needs the spoken tens
# too («schalt in dreißig Minuten aus»).
MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "fünfzehn": 15, "funfzehn": 15, "zwanzig": 20,
    "dreißig": 30, "dreissig": 30, "vierzig": 40,
    "fünfzig": 50, "funfzig": 50, "sechzig": 60, "neunzig": 90,
})

# The tail of a sleep command («… in <tail>»), most specific first. The tail
# keeps whatever the separable verb left behind it («30 Minuten aus»); every
# pattern here is anchored at the start and simply ignores it.
DURATIONS = (
    (c(r"^(?:einer\s+)?halben?\s+stunde\b"), 30),
    (c(r"^(?:einer|eine|einem|ein|1)\W?\s*stunde\b"), 60),
    (c(r"^(\d+|[a-zäöüß]+)\s*stunden\b"), "hours"),
    (c(r"^(\d+|[a-zäöüß]+)\s*(?:minut\w*|min\b)"), "minutes"),
)
