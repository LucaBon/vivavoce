"""Does this transcript contain the wake phrase, and what follows it?

One question, asked by two engines that must answer it the same way: the
browser's Web Speech recogniser (``static/js/wakeword.js``) and the
server-side one (``pro/vosk_wake.py``). Both hand in a line of text and a
configured phrase; both need "was it said, and what came after". Until now
only the browser could answer, in JavaScript, so the server engine had to be
a fixed-phrase acoustic model instead. This module is the Python half, and
it is a deliberate port rather than a fresh design: a household that types
"vivavoce" must not get one behaviour on the phone and another on the box.

**Why not reuse ``matching.py``'s scorer.** ``engine/matching.py`` blends
containment with ``difflib``'s ratio to rank *catalogue* candidates — it
answers "which of these hundred albums did they mean", where a soft ranking
is the whole point and there is always a winner. This answers a yes/no about
one short phrase, where a soft score has no threshold that is right in both
directions: the bench measured that a loose threshold is exactly where false
triggers live. So the rule here is the browser's rule — equal, a near-complete
prefix, or at most one edit — ported literally, comments and all.
"""

from __future__ import annotations

import unicodedata
from typing import List, Optional

# A shared prefix only counts as a mis-hearing when it covers most of the
# longer token. The browser learned this the hard way: any shared 4-character
# head is not a mis-hearing rule but an "any word that starts the same" rule,
# and bare «viva» fired «vivavoce».
PREFIX_MIN_COVERAGE = 0.75
PREFIX_MIN_LENGTH = 4


def normalize(text: str) -> str:
    """Lowercase and strip accents — the browser's ``norm()``, which is
    NFD-decompose then drop the combining marks (U+0300-U+036F)."""
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> List[str]:
    """Normalized words of ``text``, empties dropped."""
    return [t for t in normalize(text).split() if t]


def token_matches(a: str, b: str) -> bool:
    """Whether two normalized tokens are the same word as heard.

    Equal, a near-complete shared prefix (a mis-heard *ending*), or at most
    one edit. A literal port of ``tokEq()`` in ``static/js/wakeword.js``.
    """
    if a == b:
        return True
    if (len(a) >= PREFIX_MIN_LENGTH and len(b) >= PREFIX_MIN_LENGTH
            and (a.startswith(b) or b.startswith(a))
            and min(len(a), len(b)) / max(len(a), len(b))
            >= PREFIX_MIN_COVERAGE):
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    # The same single-edit walk the browser does: step together while the
    # characters agree, and on the first disagreement advance whichever side
    # is longer (or both, when equal). A second disagreement means no.
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(a) > len(b):
            i += 1
        elif len(b) > len(a):
            j += 1
        else:
            i += 1
            j += 1
    return edits + (len(a) - i) + (len(b) - j) <= 1


def _window_matches(heard: List[str], phrase: List[str], start: int) -> bool:
    """The browser's rule: one heard token per phrase token, each fuzzy."""
    return all(token_matches(heard[start + k], phrase[k])
               for k in range(len(phrase)))


def _run_length_matching(heard: List[str], phrase: List[str],
                         start: int) -> Optional[int]:
    """How many heard tokens from ``start`` spell the phrase once glued.

    The case the browser's token-by-token rule cannot see, and the one the
    bench actually measured: Vosk wrote 13 of 15 real utterances as
    ``vivavoce`` and 2 as ``viva voce``. Token-for-token, a one-word phrase
    can never match two words, so those two were silently lost — a 13%
    miss rate coming entirely from where a recogniser chose to put a space.

    Compared glued-to-glued, so it works in both directions (a phrase typed
    as two words heard as one, too). Shortest run wins, so the command that
    follows stays whole. ``None`` when no run matches.
    """
    glued_phrase = "".join(phrase)
    # A phrase of P words can be split into at most one piece per character,
    # but in practice a recogniser splits a word in two, not in five; 2*P + 1
    # is generous and keeps this loop bounded on a long transcript.
    limit = min(len(heard) - start, 2 * len(phrase) + 1)
    for length in range(1, limit + 1):
        if length == len(phrase):
            continue                 # same word count: the window rule's job
        # A different word count means a space moved, and that is already one
        # thing forgiven — so the letters have to be exactly right. Measured
        # on the 120 near-miss clips from make_wake_corpus.py --confusables:
        # allowing an edit on top of the glue as well let «la vita e voce»
        # through, because "vitavoce" is one edit from "vivavoce". Forgiving
        # both at once spends two tolerances on one mistake, and a near-miss
        # is exactly where that gets paid for. «viva voce» is unaffected:
        # glued, it IS the word.
        if "".join(heard[start:start + length]) == glued_phrase:
            return length
    return None


def command_after_wake(text: str, phrase: str) -> Optional[str]:
    """The words of ``text`` after ``phrase``, or ``None`` if it isn't there.

    ``None`` is the "no wake word here" signal, and the empty string means
    the phrase was said on its own — the two-step flow, where the next thing
    said is the command. Same contract as ``commandAfterWake()`` in the
    browser, which the whole continuous-listening state machine is built on.

    The returned tail comes from the ORIGINAL text, not the normalized one:
    it is about to be sent as a command, and «metti Anouar Brahem» must not
    arrive with its accents flattened.
    """
    wanted = tokens(phrase)
    if not wanted:
        return None
    words = (text or "").strip().split()
    heard = [normalize(w) for w in words]
    for i in range(len(heard)):
        if (i + len(wanted) <= len(heard)
                and _window_matches(heard, wanted, i)):
            return " ".join(words[i + len(wanted):])
        run = _run_length_matching(heard, wanted, i)
        if run is not None:
            return " ".join(words[i + run:])
    return None


def contains_wake(text: str, phrase: str) -> bool:
    """Whether ``phrase`` was said at all — the detector's whole question."""
    return command_after_wake(text, phrase) is not None
