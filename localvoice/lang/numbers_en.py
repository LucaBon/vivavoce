"""English spoken numbers and durations — the tables ``en.py`` exposes. See
``numbers_it.py`` for why they live beside the patterns rather than in them.
"""

from __future__ import annotations

from .base import c

NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "ninety": 90,
    # The indefinite article, which English uses as a numeral wherever a
    # duration is spoken: "in a minute", "an hour and ten minutes". Here and
    # not in NUM_WORDS, which answers "which row of the list" — "play the a"
    # is not a pick of the first one.
    "a": 1, "an": 1,
})

_NUMTOK = r"(?:\d+|[a-z]+)"

# The tail of a sleep command ("stop in <tail>"), most specific first — see
# numbers_it.py for why the order carries the half-hour forms.
DURATIONS = (
    (c(r"^half\s+an?\s+hour\b"), 30),
    (c(r"^(?:an|a|one|1)\s*hours?\s+and\s+a\s+half\b"), 90),
    (c(rf"^({_NUMTOK})\s*hours?\s+and\s+a\s+half\b"), "hours_half"),
    (c(rf"^({_NUMTOK})\s*hours?\s+and\s+({_NUMTOK})\s*(?:minut\w*|min\b)"),
     "hours_minutes"),
    (c(r"^(?:an|one|1)\W?\s*hour\b"), 60),
    (c(rf"^({_NUMTOK})\s*hours?\b"), "hours"),
    (c(rf"^({_NUMTOK})\s*(?:minut\w*|min\b)"), "minutes"),
)

# See DURATION_TAIL in numbers_it.py.
DURATION_TAIL = (r"please", r"thanks", r"exactly", r"or\s+so", r"from\s+now")
