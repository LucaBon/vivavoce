"""A numbered list, read out loud, and «metti la 2».

Two turns of one conversation, and this module is deliberately blind to where
the list came from: an artist's top tracks on TIDAL and the albums of an
artist sitting on the disk in the hall arrive here in the same shape — a
title, plus whatever it takes to play it — because somebody answering «la
seconda» is not telling us which catalogue they meant.

Split out of ``library.py``, which held both halves and had reached the
400-line ceiling. The seam is the one its own docstring already named; what
crosses it is :func:`_dispatch_play`, the verb both halves need, and it lives
here because acting on the candidate that was picked is what this module is
for.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from connectors import for_lang
from guard import Guard, is_blocked_item
from matching import (GATE, LIST_LIMIT, ActionResult, _MODE_KEY, _normalize,
                      _normalize_apart, unreachable)
from messages import get_lang, msg
from player.errors import PlayerError


# -- conversational flow: list -> choose by number ------------------------
# A list read out loud is an answer, so its speech carries ``ok=True`` — but
# ``kind="list"`` with it, because ``Router._tag`` splices its source and room
# tags only into results with no ``kind``, and a read-out is not a play to tag.
# The failure branches carry ``ok=False`` for the reason every other refusal in
# the engine does: ``handle_many`` reads it to tell a miss from a hit, and a
# question ("which artist?") is not a hit.
#
# No ``terms`` on either read-out, deliberately. They were empty before — the
# speech was a plain string — and ``terms`` drives which fragments the web
# client reads with a foreign voice. Filling them in is a change to how a list
# is spoken aloud, which is a different question from what ``ok`` says, and it
# should be answered on its own.
def top_tracks_list(
    lms, artist: Optional[str], limit: int = LIST_LIMIT, *, guard: Optional[Guard] = None
) -> Dict:
    """Return ``{'speech', 'candidates'}``. The handler reads the list aloud and
    stores ``candidates`` (title+url) in session for a follow-up choice."""
    artist = (artist or "").strip()
    if not artist:
        return {"speech": ActionResult(msg("which_artist"), ok=False),
                "candidates": []}
    if guard and guard.blocks(artist):
        return {"speech": ActionResult(msg("blocked"), ok=False, kind=GATE),
                "candidates": []}
    try:
        tracks = lms.artist_top_tracks(artist)["tracks"]
    except PlayerError:
        return {"speech": unreachable(),
                "candidates": []}
    if guard and guard.restricted:  # drop blocked tracks so they can't be chosen
        tracks = [t for t in tracks if not is_blocked_item(t, guard.blocklist)]
    tracks = tracks[:limit]
    if not tracks:
        return {"speech": ActionResult(msg("no_tracks_for", artist=artist), ok=False),
                "candidates": []}
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=t["title"]) for i, t in enumerate(tracks)
    )
    speech = ActionResult(msg("top_tracks", artist=artist, listing=listing),
                          ok=True, kind="list")
    # ``item_id`` travels beside ``url`` because a feed may carry only one of
    # them (Spotty keeps the url one level down — see lms.artist_tracks), and
    # ``_dispatch_play`` resolves it for the ONE row that gets picked rather
    # than for all five that get read out.
    candidates = [{k: t[k] for k in ("title", "url", "item_id") if k in t}
                  for t in tracks]
    return {"speech": speech, "candidates": candidates}


# Candidate 'action' -> the local-library kind it names (album/artist/track),
# used to pick the right lms.<mode>_local_<kind>() method. The action strings
# themselves are historical ("play_...") and don't change with mode.
_LOCAL_KIND = {"play_album_id": "album", "play_artist_id": "artist", "play_track_id": "track"}


def _dispatch_play(lms, candidate: Dict, *, mode: str = "play") -> bool:
    """Act on a candidate from a previously read-out list. Its 'action'/'arg'
    say how; falls back to a plain URL so both TIDAL ({'title','url'}) and
    local ({'title','action','arg'}) lists work. ``mode``: 'play' (replace the
    queue and start it), 'add' (queue at the end) or 'insert' (queue right
    after the current track) — see :func:`play_song`.

    False when there turned out to be nothing to play: an ``item_id`` that
    resolved to no url. Nothing is sent then. ``play_url(None)`` used to go out
    as the string ``"None"``, and the reply still said «Riproduco»."""
    kind = _LOCAL_KIND.get(candidate.get("action"))
    if kind:
        getattr(lms, f"{mode}_local_{kind}")(candidate.get("arg"))
        return True
    url = candidate.get("arg") or candidate.get("url")
    if not url and candidate.get("item_id"):
        url = lms.track_url(candidate["item_id"])
    if not url:
        return False
    getattr(lms, f"{mode}_url")(url)
    return True


def choose_from(
    lms,
    candidates: Optional[List[Dict]],
    number: Optional[int],
    *,
    mode: str = "play",
    guard: Optional[Guard] = None,
) -> ActionResult:
    """Act on the N-th candidate from a previously read-out list (mode: see
    :func:`play_song`)."""
    if not candidates:
        return ActionResult(msg("no_open_list"), ok=False)
    if number is None or number < 1 or number > len(candidates):
        return ActionResult(msg("pick_range", n=len(candidates)), ok=False)
    chosen = candidates[number - 1]
    if guard and guard.blocks_item(chosen):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        if not _dispatch_play(lms, chosen, mode=mode):
            return ActionResult(msg("no_track_found", title=chosen["title"]),
                                ok=False)
    except PlayerError:
        return unreachable()
    key = _MODE_KEY[mode]
    return ActionResult(
        msg(key, name=chosen["title"]), ok=True, terms=[chosen["title"]]
    )


def _is_the_whole_request(title: str, query: str, filler) -> bool:
    """Whether ``title`` occurs in ``query`` and is the whole of what it asks.

    This is what keeps an open list from eating the next request. Step 2 of
    :func:`choose_by_name` accepts a title that merely OCCURS inside what was
    said, and a list stays pickable for five minutes: «quali brani dei Pink
    Floyd», then «metti Money for Nothing dei Dire Straits», and the «Money»
    on the list won a sentence that was never about it. The same trap catches
    «Time After Time» against a listed «Time», and it is silent — something
    plays, and it is the wrong thing.

    An article or a noun the request could have done without is not content —
    «metti l'album Fragile» is still a pick of "Fragile" — so the surrounding
    words are checked against the language's ``PICK_FILLER``. Anything else,
    a band name most of all, and this was a new request: the caller gets
    ``None`` and routes it to a fresh search, which is where it was going
    before the list ever opened.

    Both arguments arrive normalized, and the caller asks twice — once with
    the apostrophe deleted and once with it separating — because «l'album»
    folds to "lalbum" in the first form, which is no word any table can hold.
    See :func:`matching._normalize_apart`, which exists for this.
    """
    found = re.search(rf"\b{re.escape(title)}\b", query) if title else None
    if not found:
        return False
    rest = query[:found.start()] + " " + query[found.end():]
    return all(word in filler for word in rest.split())


def choose_by_name(
    lms,
    candidates: Optional[List[Dict]],
    name: Optional[str],
    *,
    mode: str = "play",
    guard: Optional[Guard] = None,
) -> Optional[ActionResult]:
    """Act on the candidate whose title matches ``name`` from a previously
    read-out list (mode: see :func:`play_song`). Returns ``None`` when
    there's no list, no name, or no title matches, so the caller falls back
    to a fresh search. ``None`` is deliberately *not* a 'Non ...' miss
    string: it means 'this wasn't a selection, keep routing'."""
    if not candidates:
        return None
    query = _normalize(name)
    if not query:
        return None
    chosen = None
    for cand in candidates:  # 1) exact normalized title match wins
        if _normalize(cand.get("title")) == query:
            chosen = cand
            break
    if chosen is None:  # 2) whole-word match either direction
        filler = for_lang(get_lang()).pick_filler
        apart = _normalize_apart(name)
        for cand in candidates:
            title = _normalize(cand.get("title"))
            if not title:
                continue
            if re.search(rf"\b{re.escape(query)}\b", title):
                chosen = cand      # the request is part of this title
                break
            if (_is_the_whole_request(title, query, filler)
                    or _is_the_whole_request(
                        _normalize_apart(cand.get("title")), apart, filler)):
                chosen = cand      # this title is the whole of the request
                break
    if chosen is None:
        return None
    if guard and guard.blocks_item(chosen):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        if not _dispatch_play(lms, chosen, mode=mode):
            return ActionResult(msg("no_track_found", title=chosen["title"]),
                                ok=False)
    except PlayerError:
        return unreachable()
    key = _MODE_KEY[mode]
    return ActionResult(
        msg(key, name=chosen["title"]), ok=True, terms=[chosen["title"]]
    )
