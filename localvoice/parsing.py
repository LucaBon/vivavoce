"""Word-level parsing the router does before it dispatches anything.

Spoken numbers and durations, and the names of the music sources. Split out of
``router.py`` because none of it is dispatch: it holds no state, it is the
vocabulary the dispatch is written in, and it is the part of that module the
language packs talk to rather than a listener.
"""

from __future__ import annotations

import re

from lang import PACKS
from messages import msg


# The word tables are merged across every registered language on purpose:
# the recogniser's language and the phrasing don't always agree ("metti la
# three"), and a merged lookup answers both for free.
_NUM_WORDS = {}
_ORDINAL_WORDS = {}
_MINUTE_WORDS = {}
for _pack in PACKS.values():
    _NUM_WORDS.update(_pack.NUM_WORDS)
    _ORDINAL_WORDS.update(_pack.ORDINAL_WORDS)
    _MINUTE_WORDS.update(_pack.MINUTE_WORDS)


def _as_number(token, ordinals=False):
    """A spoken position -> int, or None if the token isn't a number."""
    token = (token or "").strip().lower()
    if token.isdigit():
        return int(token)
    number = _NUM_WORDS.get(token)
    if number is None and ordinals:
        number = _ORDINAL_WORDS.get(token)
    return number


def _parse_minutes(tail):
    """A spoken duration ('30 minuti', "mezz'ora", 'an hour') -> minutes, or
    None when the tail isn't a duration (then the phrase wasn't a sleep
    command and routing falls through). Tries every language's DURATIONS in
    pack order. Those patterns are *mostly* language-disjoint; the generic
    minute form is not — German's ``30 minuten`` and Italian's ``30 minuti``
    are the same regex once ``minut`` plus a wildcard has done its work, so
    whichever pack
    comes first answers. It reads the token through the merged MINUTE_WORDS
    table either way, so the two paths cannot disagree."""
    t = (tail or "").strip().lower()
    for pack in PACKS.values():
        for pattern, spec in pack.DURATIONS:
            m = pattern.match(t)
            if not m:
                continue
            if spec == "hours":
                token = m.group(1)
                hours = (int(token) if token.isdigit()
                         else _MINUTE_WORDS.get(token))
                return hours * 60 if hours else None
            if spec == "minutes":
                token = m.group(1)
                return int(token) if token.isdigit() else _MINUTE_WORDS.get(token)
            return spec
    return None


# Web Speech rarely transcribes the service names right — they aren't real
# words, so each recognizer writes what it hears in its own language:
#   qobuz -> it «kobuz»/«cobus», en "kaboots"/"cabooze", es «cobús»/«cobos»/
#            «que bus», de «Kobutz»/«Kobuts»/«Kobus», fr «cobusse»/«kobuze»
#   tidal -> it «taidal»/«tidol», en "title", es «Vidal»/«tídal»,
#            de «Titel»/«Taidel»/«Tiedal», fr «tidale»/«tidalle»
# The explicit-source phrase must match what was *heard*, so each service name
# expands to a sound-alike pattern instead of the literal spelling.
_SERVICE_SOUNDS = {
    "tidal": r"(?:t(?:ai|ay|ei|ie|i|í|y)[\s\-]?d[aeoà]?l{1,2}e?"
             r"|titles?|titel|tider|tida|vidal)",
    "qobuz": r"(?:[qkc](?:u?[oóa]|ue)[\s\-]?b(?:oo|[uoaúù])[\s\-]?"
             r"(?:ts|tz|zz|ss|z|s)e?)",
    # Spotify needs far less of this than the other two: it is a household
    # name, so recognizers have it in their vocabulary and mostly write it
    # correctly. The variants are the tail — the final syllable is the only
    # part that drifts, and the plugin's own name leaks through now and then.
    "spotify": r"(?:spo[\s\-]?ti[\s\-]?f(?:y|ai|ay|i|ie)|spotty)",
}


def _service_re(name: str) -> str:
    """Regex snippet matching a service name as ASR may transcribe it."""
    return _SERVICE_SOUNDS.get(name, re.escape(name))


# Display names for the source tag in play confirmations.
_SERVICE_LABELS = {"tidal": "TIDAL", "qobuz": "Qobuz", "spotify": "Spotify"}


def _source_suffix(name) -> str:
    """The localized ' da TIDAL' / ' from your music' tag for a source name
    ('local' or a service), so play replies say which source answered."""
    if not name:
        return ""
    if name == "local":
        return msg("from_local")
    return msg("from_service", service=_SERVICE_LABELS.get(name, name))
