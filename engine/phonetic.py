"""Catalog-aware correction of mangled ASR transcripts (the "fatta blina" fix).

ASR models recognizing Italian speech routinely garble foreign titles into
similar-*sounding* native words ("Comfortably Numb" -> "fatta blina",
"Audioslave" -> "sfigati"). A cloud assistant fixes this by biasing its
recognizer on a planet-sized catalog; we have something better — the user's
OWN library. This module matches a mangled query against the known entity
names (local artists/albums/titles) by *sound*, not spelling, and proposes
corrected alternatives that ``Router.handle_many`` tries after the originals.

The match is deliberately conservative: corrections are only *appended* as
extra alternatives, so a query that already hits keeps its exact behaviour and
a bad suggestion costs nothing (a miss is side-effect-free).
"""

from __future__ import annotations

import difflib
import re
import threading
import unicodedata
from typing import Dict, Iterable, List, Tuple

# A correction is worth suggesting from this phonetic similarity up. Below it
# the sound overlap is coincidence-grade and would only add junk alternatives.
SUGGEST_SCORE = 0.62
# How many corrections one alternative may spawn (best-scoring first).
SUGGEST_LIMIT = 2

# ASR mishearings cross these consonant families far more often than they
# cross between them (voiced/voiceless pairs, sibilants, nasals); vowels carry
# almost no identity through a mishearing, so they all collapse to one symbol
# — but they are kept, because word length and rhythm DO survive.
_CLASSES = {
    "b": "p", "p": "p",
    "d": "t", "t": "t",
    "g": "k", "k": "k", "c": "k", "q": "k",
    "v": "f", "f": "f", "w": "f",
    "s": "s", "z": "s", "x": "s",
    "m": "n", "n": "n",
    "l": "l", "r": "r",
    "j": "a", "y": "a", "h": "",
    "a": "a", "e": "a", "i": "a", "o": "a", "u": "a",
}


def _normalize(text) -> str:
    """Lowercase + strip accents + keep word chars only, space-collapsed."""
    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]+", " ", stripped).strip()


def phonetic_key(text) -> str:
    """A sound-skeleton of ``text``: consonant classes + neutral vowels, double
    letters collapsed, spaces dropped ('Comfortably Numb' -> 'kanfartaplananp',
    'fatta blina' -> 'fataplana' — close by sound, far by spelling)."""
    norm = _normalize(text)
    out = []
    for ch in norm:
        if ch.isspace():
            continue
        mapped = _CLASSES.get(ch, ch)
        if mapped and (not out or out[-1] != mapped):
            out.append(mapped)
    return "".join(out)


def similarity(heard, name) -> float:
    """How plausibly ``heard`` is a mis-hearing of ``name``, in 0..1.

    Blends the raw spelling ratio (catches near-correct transcripts) with the
    phonetic-key ratio (catches sound-alike garbling); whichever explains the
    pair better wins."""
    h_norm, n_norm = _normalize(heard), _normalize(name)
    if not h_norm or not n_norm:
        return 0.0
    if h_norm == n_norm:
        return 1.0
    h_key, n_key = phonetic_key(heard), phonetic_key(name)
    if not h_key or not n_key:
        return 0.0
    # A mishearing keeps roughly the utterance length; wildly different
    # lengths are not the same phrase misheard.
    ratio_len = len(h_key) / len(n_key)
    if ratio_len < 0.45 or ratio_len > 2.2:
        return 0.0
    raw = difflib.SequenceMatcher(None, h_norm, n_norm).ratio()
    pho = difflib.SequenceMatcher(None, h_key, n_key).ratio()
    return max(raw, pho)


class EntityIndex:
    """The known entity names (library artists/albums/titles), queryable by
    sound. Thread-safe: the server rebuilds it from a background thread while
    request threads read it."""

    def __init__(self) -> None:
        self._entries: List[Tuple[str, str]] = []  # (name, phonetic key)
        self._lock = threading.Lock()

    def build(self, names_by_kind: Dict[str, Iterable[str]]) -> None:
        """Replace the index contents. ``names_by_kind`` maps any label (kind
        is not used for matching, artists/albums/titles alike) to names."""
        seen = set()
        entries: List[Tuple[str, str]] = []
        for names in (names_by_kind or {}).values():
            for name in names or []:
                norm = _normalize(name)
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                key = phonetic_key(name)
                if key:
                    entries.append((str(name).strip(), key))
        with self._lock:
            self._entries = entries

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def suggest(self, heard, limit: int = SUGGEST_LIMIT) -> List[Tuple[float, str]]:
        """Entity names ``heard`` plausibly is, as ``[(score, name), ...]``
        best-first; empty when nothing clears :data:`SUGGEST_SCORE`. Exact
        matches are excluded — they need no correction."""
        h_norm = _normalize(heard)
        if not h_norm:
            return []
        with self._lock:
            entries = self._entries
        h_key = phonetic_key(heard)
        if not h_key:
            return []
        # Cheap prefilter (character-multiset overlap on the sound keys) so a
        # ten-thousand-title library doesn't cost a full SequenceMatcher each.
        # The heard key sits in seq2, whose stats SequenceMatcher caches; only
        # seq1 changes per entry.
        matcher = difflib.SequenceMatcher(None, "", h_key)
        scored: List[Tuple[float, str]] = []
        for name, key in entries:
            matcher.set_seq1(key)
            if matcher.quick_ratio() < SUGGEST_SCORE:
                continue
            score = similarity(heard, name)
            if score >= SUGGEST_SCORE and _normalize(name) != h_norm:
                scored.append((score, name))
        scored.sort(key=lambda s: -s[0])
        return scored[:limit]
