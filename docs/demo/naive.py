"""What a typical voice assistant would have played, for the page to compare.

The demo exists to show one promise — never the wrong track in silence — and
a promise with nothing beside it is only a claim. So the page puts, next to
what Vivavoce did, what *the first search hit* would have been: the thing a
listener gets from an assistant that turns a sentence into keywords and plays
whatever the catalogue ranks first.

The rule is written on the page, and it is kept fair on purpose. It gets the
same sentence Vivavoce got, understands the same play verbs (the language
pack's own ``generic_play``, not a copy of it) and searches the same shelf,
ranked the same way — :data:`hifi.CATALOGUE` order, which is that
catalogue's popularity. What it does *not* do is what Vivavoce is for: read
«di Hans Zimmer» as a constraint rather than two more keywords, and say «non
ce l'ho» rather than play the nearest thing. Where those never come into it —
«metti Time dei Pink Floyd», «metti l'album Inception» — it plays the same
record, and the page says so.

Only a request to play something gets a comparison. A pause, a seek, a pick
from a numbered list is the same command on any assistant; :data:`NOT_A_PLAY`
says so rather than inventing a difference.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from hifi import CATALOGUE, _track, _words

#: Keywords shorter than this are dropped, as a keyword search drops them:
#: without it «the» in «play the album Inception» would find «The Dark Side
#: of the Moon» and the comparison would be against a straw man.
MIN_KEYWORD = 4

#: :func:`naive_turn`'s answer when the phrase does not ask to play anything.
NOT_A_PLAY = "n/a"


def _pack(lang: str):
    from lang import PACKS

    return PACKS.get(lang) or PACKS["it"]


def request_tail(text: str, lang: str) -> Optional[str]:
    """What follows the play verb, or None when this is not a play request
    (no play verb, or a pick from a list: «metti la 2», «play number 2»)."""
    said = " ".join((text or "").lower().split())
    patterns = _pack(lang).PATTERNS
    for key in ("choose_number", "choose_article"):
        if patterns[key].fullmatch(said):
            return None
    found = patterns["generic_play"].search(said)
    if not found:
        return None
    return found.group(found.lastindex or 0)


def keywords(tail: str) -> List[str]:
    return [w for w in _words(tail) if len(w) >= MIN_KEYWORD and not w.isdigit()]


def naive_pick(text: str, lang: str = "it") -> Optional[Dict[str, Any]]:
    """The first track, in catalogue order, sharing any keyword with the
    request — or None when nothing shares one."""
    tail = request_tail(text, lang)
    wanted = set(keywords(tail or ""))
    if not wanted:
        return None
    for n, (title, artist, album, _) in enumerate(CATALOGUE):
        if wanted & set(_words(" ".join((title, artist, album)))):
            return _track(n)
    return None


def naive_turn(text: str, lang: str = "it") -> Union[str, None, Dict[str, str]]:
    """For the page: ``"n/a"``, None (it would have found nothing), or the
    track it would have started."""
    tail = request_tail(text, lang)
    if tail is None or not keywords(tail):
        return NOT_A_PLAY
    track = naive_pick(text, lang)
    if track is None:
        return None
    return {"title": track["title"], "artist": track["artist"],
            "album": track["album"], "url": track["url"]}
