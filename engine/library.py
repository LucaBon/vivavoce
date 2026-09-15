"""The local library: Music Folder, USB, whatever the server has indexed.

The only catalogue this engine can search without asking anyone's permission,
and therefore the only one the room gate is willing to be decided by
(:func:`library_candidates`).

What it finds is offered the way anything else is — a numbered list, or one
record simply put on — so the turn that answers «la seconda» lives next door
in :mod:`candidates`, together with :func:`_dispatch_play`, the one verb this
module borrows from there.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from candidates import _dispatch_play
from guard import Guard, is_blocked_item
from matching import (GATE, LIST_LIMIT, LOCAL_CONFIDENT, ActionResult,
                      _MODE_SUFFIX, _dedup_by_title_artist, _did_you_mean,
                      _score, _strip_lead_filler)
from messages import msg
from player.errors import PlayerError
from player.protocols import service_label


# -- local library (Music Folder / USB) -----------------------------------
# On a score tie the category order used to decide, and it listed albums
# first: asking for an artist whose name is also one of their album titles
# played the album. Preference order when scores are equal.
_LOCAL_KIND_RANK = {"artist": 0, "track": 1, "album": 2}


#: The ``kind`` of a local miss that is not a miss: the library HAS what was
#: asked for, and cannot play it, because the rows were imported by a streaming
#: plugin that is logged out (see ``LMSClient.blocking_service``). It is its own
#: kind because the two answers a caller owes are opposite ones — the source
#: selector moves on to a service that can play it, and someone who asked for
#: their own library by name has to be told why it went quiet.
IMPORT_OFFLINE = "import_offline"


def _import_offline(lms, query, blocked) -> ActionResult:
    """The library has it; the plugin that owns the audio is logged out."""
    return ActionResult(
        msg("local_import_offline", query=query,
            service=service_label(lms, sorted(blocked)[0])),
        ok=False, kind=IMPORT_OFFLINE)


def _local_group(lms, cands, query, kind, action, guard, blocked=None):
    """Confident, distinct candidates for one category, each scored by its own name
    (album/track by title, artist by name) and turned into a choose_from-ready dict.

    A row whose audio belongs to a streaming plugin that is logged out is left
    out, and the service that blocked it is added to ``blocked`` — see
    ``LMSClient.blocking_service``. A library that offers a record it cannot
    play is worse than one that admits it hasn't got it: the app announced
    "playing", LMS accepted the command, and the room stayed silent. Dropping
    it here means the request carries on to a service that CAN play it, and
    ``blocked`` is what lets the caller say so out loud when the user asked for
    the library by name.

    The check runs after the score cut on purpose: it is free for a row on a
    disk and one query for an imported one, so only rows that actually matched
    the words can cost anything."""
    out = []
    for c in cands:
        if guard and guard.restricted and is_blocked_item(c, guard.blocklist):
            continue
        s = _score(query, c.get("title"))
        if s < LOCAL_CONFIDENT:
            continue
        offline = lms.blocking_service(c, kind)
        if offline:
            if blocked is not None:
                blocked.add(offline)
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
    except PlayerError:
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
        blocked = set()
        groups = [
            g for g in (
                _local_group(lms, lms.local_album_candidates(query), query, "album", "play_album_id", guard, blocked),
                _local_group(lms, lms.local_artist_candidates(query), query, "artist", "play_artist_id", guard, blocked),
                _local_group(lms, lms.local_track_candidates(query), query, "track", "play_track_id", guard, blocked),
            ) if g
        ]
        if not groups:
            if blocked:
                return _import_offline(lms, query, blocked)
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
    except PlayerError:
        return ActionResult(msg("err_unreachable"), ok=False)


def play_local_artist(lms, query: Optional[str], *,
                      guard: Optional[Guard] = None) -> ActionResult:
    """«metti canzoni di X» against the local library: play the ARTIST.

    :func:`play_local` is the GENERIC resolver — it searches albums, artists
    and tracks and lets the best-scoring category win — and that is exactly
    wrong for a request that already said which category it means. A band
    whose name also matches two tracks got "intendevi?" read back at it
    instead of its music, which is the defect this exists to close.

    Only artist rows are scored here, so the question is asked only when
    several ARTISTS are genuinely close, and the answer is the whole
    discography (``playlistcontrol artist_id:``) rather than one album of it.

    No fallback to :func:`play_local` when no artist matches. The request
    named a category; answering it with a different one is the mistake above,
    and ``local_no_artist`` says the true thing instead.
    """
    query = _strip_lead_filler(query)
    if not query:
        return ActionResult(msg("ask_artist"), ok=False)
    if guard and guard.blocks(query):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        blocked = set()
        scored = _local_group(lms, lms.local_artist_candidates(query), query,
                              "artist", "play_artist_id", guard, blocked)
        if not scored:
            if blocked:
                return _import_offline(lms, query, blocked)
            return ActionResult(msg("local_no_artist", artist=query), ok=False)
        distinct = _dedup_by_title_artist([cand for _s, cand in scored])
        if len(distinct) >= 2:
            return _did_you_mean(query, distinct)
        item = distinct[0]
        _dispatch_play(lms, item)
        return ActionResult(msg("playing_local", title=item["title"]),
                            ok=True, terms=[item["title"]])
    except PlayerError:
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
    except PlayerError:
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
