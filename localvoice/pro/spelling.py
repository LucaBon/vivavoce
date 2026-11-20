# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Other ways to spell what was heard, that sound exactly the same
(phase 4 of docs/name-recognition-design.md).

For a name nobody in the house has played yet, there is no index to consult:
«camin» is all there is. But the recogniser wrote it in the only spelling
Italian has for the sound, and a catalogue keyed by letters may hold it as
«Kamin». So the same sound is respelt the ways a foreign name often is —
c→k, i→y at the end, f→ph, v→w, «gi» + vowel → j — and each respelling the
catalogue is *asked* about, never played: :meth:`pro.names.Names.respell`
decides from what comes back.

A respelling is kept only if its phonetic key is identical to the original's
(:func:`pro.phonetic.phonetic_key`): this module invents spellings, never
sounds. «scena» → «shena» is dropped in Italian, because «sc» before e is
not the sound «sh» is read as.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from matching import parse_song_query
from pro.name_index import _entry_score
from pro.naming import _decide, _phrase
from pro.phonetic import fold, phonetic_key

#: How many respellings of a request are looked up. Each is one catalogue
#: search inside the turn's ten seconds, after the ordinary search has
#: already spent some of them.
MAX_VARIANTS = 2

#: Each rule: a spelling a recogniser writes, and the one a foreign name may
#: use for the same sound. All of them together first — «gioni» is «jony»
#: more often than it is «joni» or «giony» — then one at a time, in this
#: order: the most common mismatch first.
_Rule = Tuple["re.Pattern[str]", str]


def _rules(*pairs: Tuple[str, str]) -> List[_Rule]:
    return [(re.compile(p), r) for p, r in pairs]


_COMMON = _rules(
    (r"c(?=[aou])", "k"),     # camin -> kamin
    # joni -> jony; not «dei», «lei», «noi»: after a consonant, in a word
    # of four letters or more.
    (r"(?<=\w\w[^aeiou\W])i\b", "y"),
    (r"f", "ph"),             # filip -> philip
    (r"v", "w"),              # vagner -> wagner (sounds the same only where
                              # the language reads w as v; the key decides)
)

_RULES: Dict[str, List[_Rule]] = {
    "it": _rules(
        (r"c(?=[aou])", "k"),     # the commonest of all, ahead of the rest
        (r"ch(?=[ei])", "k"),     # chiara -> kiara
        (r"cu(?=[aeiou])", "qu"),  # cuin -> quin
        (r"gi(?=[aou])", "j"),    # gioni -> joni
    ) + _COMMON,
    "en": _rules((r"k(?=[aou])", "c"), (r"y\b", "ie")) + _COMMON,
    "de": _rules((r"k", "c"), (r"f", "v")) + _COMMON,
    "fr": _rules((r"k", "qu"), (r"ou", "u")) + _COMMON,
    "es": _rules((r"k", "c"), (r"b", "v")) + _COMMON,
}


def spelling_variants(text: str, lang: str = "it", limit: int = 2) -> List[str]:
    """Up to ``limit`` other spellings of ``text`` that sound identical,
    most likely first. ``text`` is folded first (lower case, no accents):
    a catalogue search does not care about either.
    """
    original = fold(text)
    if not original:
        return []
    key = phonetic_key(original, lang)
    rules = _RULES.get(lang, _RULES["it"])
    combined = original
    for pattern, repl in rules:
        combined = pattern.sub(repl, combined)
    candidates = [combined] + [pattern.sub(repl, original)
                               for pattern, repl in rules]
    out: List[str] = []
    for variant in candidates:
        if (variant != original and variant not in out
                and phonetic_key(variant, lang) == key):
            out.append(variant)
    return out[:limit]


def respell(queries: List[str], lang: str,
            search: Callable[[str], list]) -> Optional[dict]:
    """The first of ``queries`` whose respelling the catalogue holds, as
    ``{"index", "text", "title", "artist"}`` — or None.

    «camin» is respelt «kamin» (:func:`spelling_variants`), and ``search`` —
    a catalogue lookup that plays nothing — is asked about it. A title that
    comes back sounding like what was heard, over the threshold and ahead of
    anything else that came back by the margin (:func:`pro.naming._decide`),
    is the answer. A search that fails — the system, or the turn's time, has
    run out — ends the attempt: it is a bonus, not a reason to wait.
    """
    for i, query in enumerate(queries):
        parsed = parse_song_query(query, lang=lang)
        title, artist = parsed.get("title"), parsed.get("artist")
        if not title:
            continue
        for variant in spelling_variants(title, lang, limit=MAX_VARIANTS):
            try:
                rows = search(f"{variant} {artist}" if artist else variant)
            except Exception:  # noqa: BLE001 — out of time or not answering
                return None
            scored = []
            for row in rows or []:
                entry = {"title": row.get("title"), "artist": row.get("artist"),
                         "kind": "track"}
                score = _entry_score(entry, title, artist or "", lang)
                if score > 0:
                    scored.append((score, entry))
            scored.sort(key=lambda s: -s[0])
            entry = _decide(scored, heard_artist=bool(artist))
            if entry is None or fold(entry.get("title")) == fold(title):
                continue
            return {"index": i,
                    "text": _phrase(entry, lang, with_artist=bool(artist)),
                    "title": entry.get("title"), "artist": entry.get("artist")}
    return None
