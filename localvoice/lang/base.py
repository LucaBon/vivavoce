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

**A pack module holds the grammar; the word lists live beside it.** ``xx.py``
is ``PATTERNS`` and nothing else; ``moods_xx.py`` and ``numbers_xx.py`` hold
the five data tables of the contract above, ``words_xx.py`` holds the closed
sets those patterns are built from, and the pack re-exports them all so this
contract is unchanged. The seam is real and not bookkeeping: a regex encodes how a
language is *shaped*, a table only what it happens to *say*, the tables are
what ``parsing.py`` merges across every pack, and ``MOOD_WORDS`` is what
``engine/moods.py`` will one day read from generated data. It is also where
the growth is — the size guard in ``tests/test_packaging.py`` is what said so,
twice, when German went over the line on the strength of its vocabulary alone.
A module without ``CODE`` is invisible to the registry, so all six sit here
without being mistaken for packs — the same way this file does.
"""

from __future__ import annotations

import re


def c(pattern: str):
    """Compiled, case-insensitive — every pack builds its patterns with this."""
    return re.compile(pattern, re.I)
