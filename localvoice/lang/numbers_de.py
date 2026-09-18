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

_NUMTOK = r"(?:\d+|[a-zäöüß]+)"

# The tail of a sleep command («… in <tail>»), most specific first — see
# numbers_it.py for why the order carries the half-hour forms. «anderthalb»
# and «eineinhalb» are the reason German needed them most: read by the plain
# hour pattern, «in anderthalb Stunden» parsed as nothing at all and the
# phrase fell through to ``pause_explicit``, which paused the music on the
# spot instead of in ninety minutes.
DURATIONS = (
    (c(r"^(?:einer\s+)?halben?\s+stunde\b"), 30),
    (c(r"^(?:anderthalb|eineinhalb)\s*stunden?\b"), 90),
    (c(rf"^({_NUMTOK})\s*stunden?\s+und\s+({_NUMTOK})\s*(?:minut\w*|min\b)"),
     "hours_minutes"),
    (c(r"^(?:einer|eine|einem|ein|1)\W?\s*stunde\b"), 60),
    (c(rf"^({_NUMTOK})\s*stunden\b"), "hours"),
    (c(rf"^({_NUMTOK})\s*(?:minut\w*|min\b)"), "minutes"),
)

# German is why this table exists at all. The sleep pattern in de.py captures
# everything after «in», and German writes the rest of its verb *after* the
# duration — «in 30 Minuten aus», «in 30 Minuten ausschalten», «in 30 Minuten
# auf zu spielen» — so "the whole tail has to be a duration" would refuse the
# three most ordinary phrasings the language has. These are the words that may
# be left over; every pack declares its own, see numbers_it.py.
#
# The verb half is the same alternation de.py's ``sleep`` pattern requires,
# written out again rather than imported: the two answer different questions
# (is a stop verb PRESENT anywhere / may this word be left OVER), and a shared
# constant would make the next edit to one of them silently an edit to both.
DURATION_TAIL = (r"(?:aus|ab|an|ein)?schalt\w*", r"stopp?\w*", r"pausier\w*",
                 r"aufh(?:ö|oe)ren", r"schluss",
                 r"aus", r"ab", r"an", r"auf",
                 r"zu\s+spielen", r"zu\s+h(?:ö|oe)ren",
                 r"bitte", r"danke", r"genau", r"ungef(?:ä|ae)hr")
