"""The language-pack contract (and its one shared helper).

A *pack* is a module in this package that declares how one spoken language
maps onto the router's intents. The router owns all the logic (dispatch,
state, kid-safe, multi-room); a pack owns nothing but data:

``CODE``
    The BCP-47-ish language code the web client sends (``"it"``, ``"en"``).

``PATTERNS``
    Dict of compiled regexes, one entry per routing step (see ``it.py`` for
    the canonical key list — ``tests/test_english.py`` asserts key parity
    between languages). The ``service`` entry is a **template string**, not a
    compiled regex: the router expands ``{s}`` per streaming service with its
    ASR sound-alike pattern.

``NUM_WORDS`` / ``ORDINAL_WORDS``
    Spoken positions -> int ("tre"/"three", "seconda"/"second"). The router
    merges the tables of every registered pack, so a pick keeps working when
    the recogniser answers in the "wrong" language.

``MINUTE_WORDS``
    Spoken durations for the sleep timer, beyond the list positions
    ("trenta"/"thirty"). Merged like the number tables.

``MOOD_WORDS``
    Spoken tail -> mood key for a vague request ("rilassante"/"relaxing" ->
    ``relax``), resolved against the table in ``engine/moods.py``. Keys are
    written already normalized — lowercase, no accents, no apostrophes — and
    matched against the *whole* tail: a partial match is how a song title
    would become a mood. The pack also owns the two patterns that reach here,
    ``mood`` and ``mood_another``.

``DURATIONS``
    Tuple of ``(compiled_regex, spec)`` tried in order against the tail of a
    sleep command ("spegni tra <tail>"). ``spec`` is an int (fixed minutes),
    ``"hours"`` (group 1 is a number of hours) or ``"minutes"`` (group 1 is a
    number or a MINUTE_WORDS token).

Adding a language is adding one module with these seven names (plus its
message catalog in ``engine/catalogs/`` and a test suite modeled on
``tests/test_english.py``); the registry in ``__init__.py`` finds it by
itself.

``MOOD_WORDS`` lives in a module of its own — ``moods_it.py``, ``moods_en.py``,
``moods_de.py`` — and each pack re-exports it. It is a word list rather than
grammar, it is the half ``engine/moods.py`` will one day read from generated
data, and it is the half that grows: the size guard in
``tests/test_packaging.py`` is what said so, when German went over the line on
the strength of its vocabulary alone. A module without ``CODE`` is invisible to
the registry, so those three sit here without being mistaken for packs — the
same way this file does.
"""

from __future__ import annotations

import re


def c(pattern: str):
    """Compiled, case-insensitive — every pack builds its patterns with this."""
    return re.compile(pattern, re.I)
