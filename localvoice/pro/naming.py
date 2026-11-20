# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Deciding on a name: from a ranking of candidates that sound like what was
heard, the one to use — or none — and how to say it in a request.

Shared by the two places a name is chosen for a misheard one: the index of
names this household has played (``names.py``, step 1c) and the respellings
looked up in the catalogue (``spelling.py``, phase 4). Same threshold, same
margin, same refusal to choose between two names that both fit.
"""

from __future__ import annotations

from typing import Optional

from pro.phonetic import fold

#: How close a known name has to sound to what was heard to replace it.
#: «camin»/«Kamin» is 1.0; «emin»/«Eminem», two different artists, is 0.8 —
#: which is why this is not lower. Measured in tests/test_phonetic.py.
ACCEPT = 0.9

#: How far ahead of the runner-up the best name has to be. Two known names
#: that both sound like what was heard are a question, not an answer, and
#: the turn is left as it was.
MARGIN = 0.1

#: The word that joins a title to its artist, per language — one that
#: ``parse_song_query`` splits on (engine/connectors/), so the sentence
#: rebuilt here is read back as the title and the artist it names.
BY = {"it": "di", "en": "by", "de": "von", "fr": "par", "es": "de"}


def _decide(ranked, *, heard_artist: bool) -> Optional[dict]:
    """The known name to use, from :meth:`NameIndex.match`'s ranking, or None.

    Over :data:`ACCEPT`, and :data:`MARGIN` ahead of the next *different*
    name — the same song kept twice (played, and saved as a favourite) is one
    name, not a rival. Two songs with the same title by different artists,
    when no artist was heard, are still one answer about the title: the
    search will ask which, as it would have for a title spelt right.
    """
    seen, distinct = set(), []
    for score, entry in ranked:
        key = (fold(entry.get("title")), fold(entry.get("artist")))
        if key not in seen:
            seen.add(key)
            distinct.append((score, entry))
    if not distinct or distinct[0][0] < ACCEPT:
        return None
    best_score, best = distinct[0]
    rivals = [e for s, e in distinct[1:] if s > best_score - MARGIN]
    if not rivals:
        return best
    title = fold(best.get("title"))
    if (title and not heard_artist
            and all(fold(e.get("title")) == title for e in rivals)):
        return {"title": best.get("title"), "artist": None}
    return None


def _phrase(entry: dict, lang: str, *, with_artist: bool) -> str:
    """A known name as words a request would say: «Kamin», «Kamin di EMIN &
    JONY», or the artist alone for an artist.

    The artist only when one was heard. Not every path splits it off: the
    streaming search does (``parse_song_query``), the local library searches
    the whole phrase — so «metti camin» becomes «metti Kamin», which both
    understand, and only a request that named an artist gets one back.
    """
    title, artist = entry.get("title"), entry.get("artist")
    if title and artist and with_artist:
        return f"{title} {BY.get(lang, BY['it'])} {artist}"
    return title or artist or ""
