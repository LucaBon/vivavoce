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

# The tail of a sleep command ("spegni tra <tail>"), most specific first.
DURATIONS = (
    (c(r"^mezz\W?ora\b"), 30),
    (c(r"^(?:un|1)\W?\s*ora\b"), 60),
    (c(r"^(\d+|[a-zà-ù]+)\s*ore\b"), "hours"),
    (c(r"^(\d+|[a-zà-ù]+)\s*(?:minut\w*|min\b)"), "minutes"),
)
