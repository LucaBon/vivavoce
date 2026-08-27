"""Candidates: making them, reading them out, and acting on the one picked.

Two halves of one conversation. The first offers a numbered list — an artist\'s
top tracks, the albums you own — and the second acts on «metti la 2». In
between sits the local library itself, which is the only catalogue this engine
can search without asking anyone\'s permission, and therefore the only one the
room gate is willing to be decided by (:func:`library_candidates`).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from guard import Guard, is_blocked_item
from lms import LMSError
from matching import (GATE, LIST_LIMIT, LOCAL_CONFIDENT, ActionResult, _MODE_KEY,
                      _MODE_SUFFIX, _dedup_by_title_artist, _did_you_mean,
                      _normalize, _score, _strip_lead_filler)
from messages import msg

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
    except LMSError:
        return {"speech": ActionResult(msg("err_unreachable"), ok=False),
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
    candidates = [{"title": t["title"], "url": t["url"]} for t in tracks]
    return {"speech": speech, "candidates": candidates}


# Candidate 'action' -> the local-library kind it names (album/artist/track),
# used to pick the right lms.<mode>_local_<kind>() method. The action strings
# themselves are historical ("play_...") and don't change with mode.
_LOCAL_KIND = {"play_album_id": "album", "play_artist_id": "artist",
              "play_track_id": "track"}


def _dispatch_play(lms, candidate: Dict, *, mode: str = "play") -> None:
    """Act on a candidate from a previously read-out list. Its 'action'/'arg'
    say how; falls back to a plain URL so both TIDAL ({'title','url'}) and
    local ({'title','action','arg'}) lists work. ``mode``: 'play' (replace the
    queue and start it), 'add' (queue at the end) or 'insert' (queue right
    after the current track) — see :func:`play_song`."""
    kind = _LOCAL_KIND.get(candidate.get("action"))
    if kind:
        getattr(lms, f"{mode}_local_{kind}")(candidate.get("arg"))
    else:
        getattr(lms, f"{mode}_url")(candidate.get("arg") or candidate.get("url"))


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
        _dispatch_play(lms, chosen, mode=mode)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    key = _MODE_KEY[mode]
    return ActionResult(
        msg(key, name=chosen["title"]), ok=True, terms=[chosen["title"]]
    )


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
        for cand in candidates:
            title = _normalize(cand.get("title"))
            if not title:
                continue
            if re.search(rf"\b{re.escape(title)}\b", query) or re.search(
                rf"\b{re.escape(query)}\b", title
            ):
                chosen = cand
                break
    if chosen is None:
        return None
    if guard and guard.blocks_item(chosen):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        _dispatch_play(lms, chosen, mode=mode)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    key = _MODE_KEY[mode]
    return ActionResult(
        msg(key, name=chosen["title"]), ok=True, terms=[chosen["title"]]
    )


# -- local library (Music Folder / USB) -----------------------------------
# On a score tie the category order used to decide, and it listed albums
# first: asking for an artist whose name is also one of their album titles
# played the album. Preference order when scores are equal.
_LOCAL_KIND_RANK = {"artist": 0, "track": 1, "album": 2}


def _local_group(cands, query, kind, action, guard):
    """Confident, distinct candidates for one category, each scored by its own name
    (album/track by title, artist by name) and turned into a choose_from-ready dict."""
    out = []
    for c in cands:
        if guard and guard.restricted and is_blocked_item(c, guard.blocklist):
            continue
        s = _score(query, c.get("title"))
        if s < LOCAL_CONFIDENT:
            continue
        cand = {"title": c.get("title"), "action": action, "arg": c["id"], "_kind": kind}
        if c.get("artist"):
            cand["artist"] = c["artist"]
        out.append((s, cand))
    out.sort(key=lambda x: -x[0])
    return out


def library_candidates(lms, query: Optional[str], *,
                       guard: Optional[Guard] = None) -> List[Dict]:
    """Every local album/artist/track the LMS offers for ``query``, deduped.

    The retrieval half of :func:`play_local` with the scoring, the choosing and
    the playing left out — a genuine dry run, three read-only searches and not
    one command that touches a player. It exists because until now the only way
    to ask "does the library know this phrase?" was to call a resolver, and
    every resolver in this module answers by *playing* something.

    ``[]`` for an empty query, an empty library, or an LMS that cannot be
    reached: all three mean "no opinion", and the caller's default stands.

    ``guard`` drops what kid-safe blocks. Not belt-and-braces — the resolvers
    downstream do refuse a blocked item, but by then it has already decided the
    routing, and the refusal («c'è, ma è nella lista dei brani bloccati»)
    confirms the record is in the house where the answer it replaced leaked
    nothing.
    """
    query = _strip_lead_filler(query)
    if not query:
        return []
    if guard and guard.blocks(query):
        return []
    try:
        # count=10 apiece, as everywhere else here. Worth knowing at the call
        # site: on a big library the truncation bites the narrower query first.
        cands = (lms.local_album_candidates(query)
                 + lms.local_artist_candidates(query)
                 + lms.local_track_candidates(query))
    except LMSError:
        return []
    keep = [c for c in cands
            if c.get("title") and not (guard and guard.restricted
                                       and is_blocked_item(c, guard.blocklist))]
    return _dedup_by_title_artist(keep)


def best_match_score(query: Optional[str], items: Optional[List[Dict]], *,
                     key: str = "title", subset_floor: bool = True) -> float:
    """The best :func:`_score` of ``query`` over ``items``; ``0.0`` for none."""
    if not items:
        return 0.0
    return max(_score(query, it.get(key), subset_floor=subset_floor)
               for it in items)


def play_local(lms, query: Optional[str], *, mode: str = "play",
               guard: Optional[Guard] = None) -> ActionResult:
    """Act on the local library (mode: see :func:`play_song`). Candidates are
    scored (title, or artist name for the artist category) so a generic word
    like 'love' never plays an unrelated row; an artist query plays the
    artist, not one of their albums; and when several tracks genuinely
    match, it asks (local rows carry the artist, so the list reads
    'Love di X, Love di Y')."""
    query = _strip_lead_filler(query)
    if not query:
        return ActionResult(msg("ask_query"), ok=False)
    if guard and guard.blocks(query):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        groups = [
            g for g in (
                _local_group(lms.local_album_candidates(query), query, "album", "play_album_id", guard),
                _local_group(lms.local_artist_candidates(query), query, "artist", "play_artist_id", guard),
                _local_group(lms.local_track_candidates(query), query, "track", "play_track_id", guard),
            ) if g
        ]
        if not groups:
            return ActionResult(msg("local_not_found", query=query), ok=False)
        # Best-scoring category wins; an exact tie goes to the artist.
        groups.sort(key=lambda g: (-g[0][0],
                                   _LOCAL_KIND_RANK.get(g[0][1]["_kind"], 9)))
        winner = [cand for _s, cand in groups[0]]
        distinct = _dedup_by_title_artist(winner)
        if len(distinct) >= 2:
            return _did_you_mean(query, distinct)
        item = distinct[0]
        _dispatch_play(lms, item, mode=mode)
        suffix = _MODE_SUFFIX[mode]
        speech = (
            msg("playing_local_album" + suffix, title=item["title"])
            if item["_kind"] == "album"
            else msg("playing_local" + suffix, title=item["title"])
        )
        return ActionResult(speech, ok=True, terms=[item["title"]])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)


def local_albums_list(
    lms, artist: Optional[str], limit: int = LIST_LIMIT, *, guard: Optional[Guard] = None
) -> Dict:
    """Return ``{'speech', 'candidates'}`` listing a local artist's albums; each
    candidate plays that album by id when chosen."""
    artist = (artist or "").strip()
    if not artist:
        return {"speech": ActionResult(msg("which_artist"), ok=False),
                "candidates": []}
    if guard and guard.blocks(artist):
        return {"speech": ActionResult(msg("blocked"), ok=False, kind=GATE),
                "candidates": []}
    try:
        result = lms.local_albums_by_artist(artist)
    except LMSError:
        return {"speech": ActionResult(msg("err_unreachable"), ok=False),
                "candidates": []}
    if not result["artist"]:
        return {"speech": ActionResult(msg("local_no_artist", artist=artist), ok=False),
                "candidates": []}
    albums = result["albums"]
    if guard and guard.restricted:  # drop blocked albums so they can't be chosen
        albums = [a for a in albums if not is_blocked_item(a, guard.blocklist)]
    albums = albums[:limit]
    if not albums:
        return {"speech": ActionResult(msg("local_no_albums", artist=artist), ok=False),
                "candidates": []}
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=a["title"]) for i, a in enumerate(albums)
    )
    speech = ActionResult(
        msg("local_albums", artist=result["artist"]["title"], listing=listing),
        ok=True, kind="list")
    candidates = [
        {"title": a["title"], "action": "play_album_id", "arg": a["id"]} for a in albums
    ]
    return {"speech": speech, "candidates": candidates}
