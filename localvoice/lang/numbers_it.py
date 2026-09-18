"""Italian spoken numbers and durations — the tables ``it.py`` exposes as
``NUM_WORDS``, ``ORDINAL_WORDS``, ``MINUTE_WORDS`` and ``DURATIONS``.

Beside the patterns rather than in them, on the same terms as ``moods_it.py``:
a recogniser writes "tre", never "3", and what it may write is a word list.
``parsing.py`` merges these across every pack precisely because they are data
— a pick keeps working when the recogniser answers in the "wrong" language.
"""

from __future__ import annotations

from .base import c

# Web Speech transcribes a spoken position as a word ("tre"), not "3".
NUM_WORDS = {
    "uno": 1, "un": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
    "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
}

# People answer a read-out list with "la seconda" at least as often as with
# the bare number (see the router for how ordinals are gated on an open list).
ORDINAL_WORDS = {
    "primo": 1, "prima": 1, "secondo": 2, "seconda": 2, "terzo": 3, "terza": 3,
    "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5, "sesto": 6, "sesta": 6,
    "settimo": 7, "settima": 7, "ottavo": 8, "ottava": 8, "nono": 9, "nona": 9,
    "decimo": 10, "decima": 10,
}

# Durations go beyond list positions: the sleep timer needs the spoken tens too
# («spegni tra trenta minuti»).
MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
    "cinquanta": 50, "sessanta": 60, "novanta": 90,
})

# A spoken number as one token.
_NUMTOK = r"(?:\d+|[a-zà-ù]+)"

# The tail of a sleep command ("spegni tra <tail>"), most specific first — and
# "most specific" is not decoration: read in the other order, `^(?:un|1)\W?ora`
# matches the first two words of «un'ora e mezza» and silently drops the half.
# ``_parse_minutes`` requires the WHOLE tail to parse (see DURATION_TAIL), so a
# half nobody could read is now a phrase that does not set a timer at all
# rather than a timer half an hour short.
DURATIONS = (
    (c(r"^mezz\W?ora\b"), 30),
    (c(r"^(?:un\W?\s*|1\s*)?ora\s+e\s+mezza\b"), 90),
    (c(rf"^({_NUMTOK})\s*ore\s+e\s+mezz[ao]\b"), "hours_half"),
    # ``\W?`` and ``or[ae]``: Italian elides the article onto the noun, so
    # «un'ora e venti minuti» is one hour written without a space after it.
    (c(rf"^({_NUMTOK})\W?\s*or[ae]\s+e\s+({_NUMTOK})\s*(?:minut\w*|min\b)"),
     "hours_minutes"),
    (c(r"^(?:un|1)\W?\s*ora\b"), 60),
    (c(rf"^({_NUMTOK})\s*ore\b"), "hours"),
    (c(rf"^({_NUMTOK})\s*(?:minut\w*|min\b)"), "minutes"),
)

# What may follow a duration and still leave it a duration: politeness, and
# the words a speaker rounds with. Merged across every pack by ``parsing.py``,
# like the word tables — see DURATION_TAIL in numbers_de.py, which is the
# reason this table is not simply empty everywhere.
DURATION_TAIL = (r"per\s+favore", r"grazie", r"dai", r"esatt[eiao]", r"circa")
