"""Voice-action business logic, kept as pure functions for easy testing.

Each function takes an :class:`lms.LMSClient` (or any object with the same
methods) plus already-extracted slot values, performs the LMS/TIDAL operation,
and returns a speech string. The wording lives in the ``messages`` catalog
(referenced by key — see :mod:`messages` for the i18n plan); today the only
catalog is Italian. All LMS failures are turned into a friendly message
instead of raising, so the skill never crashes on a network hiccup.
"""

from __future__ import annotations

from typing import Dict, Optional

from guard import Guard, is_blocked_item
from lms import LMSError
from matching import (CONFIDENT_SCORE, DIDYOUMEAN_LIMIT, EXACT_SCORE, GATE,
                      ActionResult, _MODE_KEY, _MODE_KEY_BY, _MODE_SUFFIX,
                      _dedup_by_title_artist, _did_you_mean, _ndistinct_titles,
                      _covers, _normalize, _rank, _score,
                      parse_song_query)
from messages import msg


def _undo_play(lms) -> None:
    """Stop and empty what we just started. ``mode="play"`` replaces the queue,
    so this only undoes our own action — used when the artist turns out to be
    blocked and we learn it only from the now-playing status."""
    try:
        lms.clear_queue()
    except LMSError:
        pass


def _play_tidal_track(lms, track: Dict, fallback_title: Optional[str], *,
                      mode: str = "play", guard: Optional[Guard] = None) -> ActionResult:
    if guard and guard.blocks_item(track):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    if mode == "play":
        lms.play_url(track["url"])
        speech, terms = _confirm_song(lms, track, fallback_title)
        # _confirm_song may have LEARNED the artist from the now-playing
        # status: TIDAL song-search items don't always carry one, and a
        # blocked artist discovered a moment late must still not play — and
        # certainly must not be read aloud in the confirmation.
        if guard and guard.blocks(*terms):
            _undo_play(lms)
            return ActionResult(msg("blocked"), ok=False, kind=GATE)
        return ActionResult(speech, ok=True, terms=terms)
    getattr(lms, f"{mode}_url")(track["url"])
    name = track.get("title") or fallback_title
    artist = track.get("artist")
    if not artist:
        return ActionResult(msg(_MODE_KEY[mode], name=name), ok=True, terms=[name])
    return ActionResult(msg(_MODE_KEY_BY[mode], name=name, artist=artist),
                        ok=True, terms=[name, artist])


def play_song(lms, query: Optional[str], *, mode: str = "play",
              guard: Optional[Guard] = None) -> ActionResult:
    """Resolve and act on a song request. ``mode``: ``"play"`` (replace the
    queue and start it — the default, used by every existing caller),
    ``"add"`` (queue at the end: "aggiungi X alla coda") or ``"insert"``
    (queue right after the current track: "metti X dopo questa")."""
    parsed = parse_song_query(query)
    title, artist, album = parsed["title"], parsed["artist"], parsed["album"]
    if not title and not album:
        return ActionResult(msg("ask_title"), ok=False)
    if guard and guard.blocks(title, artist, album):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        if album:
            return _play_from_album(lms, title, album, mode=mode, guard=guard)
        # Search on the full text (title + artist) — TIDAL's full-text search wants
        # both — then rank/disambiguate using the parsed parts.
        search_text = " ".join(p for p in (title, artist) if p) or title
        tracks = lms.search_tracks(search_text)
        if not tracks:
            return ActionResult(msg("no_track_found", title=title), ok=False)
        return _resolve_song(lms, tracks, title, artist, mode=mode, guard=guard,
                             whole=_strip_lead_filler(query))
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)


def _resolve_song(lms, tracks, title, artist, *, mode: str = "play", guard=None,
                  whole: Optional[str] = None) -> ActionResult:
    """Pick a track, disambiguate, or ask — from the TIDAL results and the parsed
    title/artist. Candidates stay in TIDAL's own relevance order, so padded-junk
    titles ranked low never reach the shortlist. ``whole`` is the unsplit request,
    used to notice that the title/artist split was spurious."""
    # A title that merely CONTAINS a connector splits into a bogus artist:
    # «Cuore di Vetro» parses as 'Cuore' by 'Vetro', «Killed by Death» as
    # 'Killed' by 'Death'. That used to degrade gracefully; with the refusal
    # below it turns into "non ho trovato" while the exact track sits first in
    # the results. If the WHOLE request matches a candidate title, the split
    # was wrong: resolve on the whole request and forget the artist.
    if artist and whole and not _covers(whole, title):
        if any(_covers(whole, t.get("title")) for t in tracks):
            title, artist = whole, None
    exacts = [t for t in tracks if _score(title, t.get("title")) >= EXACT_SCORE]
    strong = [t for t in tracks if _score(title, t.get("title")) >= CONFIDENT_SCORE]
    # 1) An artist was named -> play the matching edition (search_tracks carries the
    #    artist, so this picks the right one among identical-title songs). Every
    #    strong hit is scanned, not just the top 3: the search returns 20, and
    #    the named artist's edition sits below the fold often enough to matter.
    if artist and strong:
        best = max(strong, key=lambda t: _score(artist, t.get("artist")))
        if _score(artist, best.get("artist")) >= CONFIDENT_SCORE:
            return _play_tidal_track(lms, best, title, mode=mode, guard=guard)
        # An artist was named and nobody in the results is them. Say so rather
        # than falling through to exacts[0]: «Yesterday di Vasco Rossi» played
        # The Beatles, and in queue mode it did that without even asking.
        # Only when the results carry artists at all — some feeds don't, and
        # then we genuinely cannot tell.
        if any(t.get("artist") for t in strong):
            return ActionResult(msg("no_track_by", title=title, artist=artist),
                                ok=False)
    # 2) Exact title match -> play TIDAL's top exact (e.g. "Money" over "Money for
    #    Nothing"). 3) No title match at all -> trust TIDAL's own ranking.
    if exacts:
        return _play_tidal_track(lms, exacts[0], title, mode=mode, guard=guard)
    if not strong:
        return _play_tidal_track(lms, tracks[0], title, mode=mode, guard=guard)
    # 4) Several strong partial matches. One song (same title) -> play the top; if
    #    genuinely different titles -> ask the top 3.
    head = strong[:DIDYOUMEAN_LIMIT]
    if guard and guard.restricted:
        head = [t for t in head if not is_blocked_item(t, guard.blocklist)]
    if not head:
        return ActionResult(msg("no_track_found", title=title), ok=False)
    if _ndistinct_titles(head) < 2:
        return _play_tidal_track(lms, head[0], title, mode=mode, guard=guard)
    return _did_you_mean(title, _dedup_by_title_artist(head))


def _confirm_song(lms, track: Dict, fallback_title: Optional[str]):
    """Confirm what's playing, adding the artist when known. Returns
    ``(speech, terms)`` where terms are the foreign name(s) in the speech. TIDAL
    song-search items carry no artist, but the now-playing status does — so we
    read it back once and use it only if the playing title matches what we just
    started (guards against status still showing the previous track)."""
    name = track.get("title") or fallback_title
    artist = track.get("artist")
    if not artist and name:
        try:
            now = lms.now_playing_info()
        except LMSError:
            now = None
        if now and _normalize(now.get("title")) == _normalize(name):
            artist = now.get("artist")
    if artist:
        return msg("playing_by", name=name, artist=artist), [name, artist]
    return msg("playing", name=name), [name]


def _play_from_album(
    lms, title: Optional[str], album: str, *, mode: str = "play",
    guard: Optional[Guard] = None
) -> ActionResult:
    result = lms.album_tracks(album)
    if not result["album"]:
        return ActionResult(msg("album_not_found", album=album), ok=False)
    album_name = result["album"]["title"] or album
    if guard and (guard.blocks_item(result["album"]) or guard.blocks(album_name)):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    suffix = _MODE_SUFFIX[mode]
    if title:
        ranked = _rank(title, result["tracks"])
        if ranked and ranked[0][0] >= CONFIDENT_SCORE:
            track = ranked[0][1]
            if guard and guard.blocks_item(track):
                return ActionResult(msg("blocked"), ok=False, kind=GATE)
            getattr(lms, f"{mode}_url")(track["url"])
            return ActionResult(
                msg("playing_track_from_album" + suffix, title=track["title"], album=album_name),
                ok=True, terms=[track["title"], album_name],
            )
        # title not found in that album -> act on the whole album instead
        getattr(lms, f"{mode}_browse_item")(result["album"]["id"])
        return ActionResult(
            msg("track_not_in_album" + suffix, title=title, album=album_name),
            ok=True, terms=[title, album_name],
        )
    getattr(lms, f"{mode}_browse_item")(result["album"]["id"])
    return ActionResult(
        msg("playing_album" + suffix, album=album_name), ok=True, terms=[album_name]
    )


def play_album(lms, album: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    album = (album or "").strip()
    if not album:
        return ActionResult(msg("ask_album"), ok=False)
    if guard and guard.blocks(album):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        cands = lms.album_candidates(album)
        if not cands:
            return ActionResult(msg("album_not_found", album=album), ok=False)
        item = _rank(album, cands)[0][1]  # best title match, not blindly the first
        if guard and guard.blocks_item(item):
            return ActionResult(msg("blocked"), ok=False, kind=GATE)
        lms.play_browse_item(item["id"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    name = item["title"] or album
    return ActionResult(msg("playing_album", album=name), ok=True, terms=[name])


def play_artist(lms, artist: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    artist = (artist or "").strip()
    if not artist:
        return ActionResult(msg("ask_artist"), ok=False)
    if guard and guard.blocks(artist):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        result = lms.artist_top_tracks(artist)
        if not result["artist"]:
            return ActionResult(msg("artist_not_found", artist=artist), ok=False)
        if guard and guard.blocks_item(result["artist"]):
            return ActionResult(msg("blocked"), ok=False, kind=GATE)
        tracks = result["tracks"]
        if not tracks:
            return ActionResult(msg("artist_unplayable", artist=artist), ok=False)
        lms.play_tracks([t["url"] for t in tracks])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_artist", artist=artist), ok=True, terms=[artist])


def play_playlist(lms, name: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    name = (name or "").strip()
    if not name:
        return ActionResult(msg("ask_playlist"), ok=False)
    if guard and guard.blocks(name):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        cands = lms.playlist_candidates(name)
        if not cands:
            return ActionResult(msg("playlist_not_found", name=name), ok=False)
        item = _rank(name, cands)[0][1]
        if guard and guard.blocks_item(item):
            return ActionResult(msg("blocked"), ok=False, kind=GATE)
        lms.play_browse_item(item["id"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_playlist", name=name), ok=True, terms=[name])


# -- favorites & radio (core LMS feature, not a plugin) --------------------
def play_favorites(lms, *, guard: Optional[Guard] = None) -> ActionResult:
    """"riproduci i preferiti": play the first playable saved favorite."""
    try:
        items = lms.favorites_items()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    cands = [it for it in items if it.get("id") and it.get("name")]
    if guard and guard.restricted:
        cands = [c for c in cands if not is_blocked_item(c, guard.blocklist)]
    if not cands:
        return ActionResult(msg("favorites_empty"), ok=False)
    chosen = cands[0]
    try:
        lms.favorites_playlist_play(chosen["id"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_favorites"), ok=True, terms=[chosen["name"]])


def play_radio(lms, name: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    """"metti radio X": search the saved favorites for a station matching X —
    the universal, plugin-agnostic way LMS/Lyrion users save internet-radio
    streams, so this works regardless of which (if any) radio app/plugin the
    server has installed."""
    name = (name or "").strip()
    if not name:
        return ActionResult(msg("ask_radio"), ok=False)
    if guard and guard.blocks(name):
        return ActionResult(msg("blocked"), ok=False, kind=GATE)
    try:
        items = lms.favorites_items(query=name)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    cands = [{"title": it.get("name"), "id": it.get("id")}
             for it in items if it.get("id") and it.get("name")]
    if guard and guard.restricted:
        cands = [c for c in cands if not is_blocked_item(c, guard.blocklist)]
    if not cands:
        return ActionResult(msg("radio_not_found", name=name), ok=False)
    score, best = _rank(name, cands)[0]
    if score < CONFIDENT_SCORE:
        return ActionResult(msg("radio_not_found", name=name), ok=False)
    try:
        lms.favorites_playlist_play(best["id"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_radio", name=best["title"]), ok=True,
                        terms=[best["title"]])

# -- the rest of the engine, still reachable from here ------------------------
#
# This module was 1054 lines and is now the streaming play family alone: the
# scoring, the blocklist, the transport controls and the local library live
# next door. It goes on re-exporting every one of their names, and not out of
# politeness — the router, the tools and a great many tests reach for
# ``actions.play_local``, ``actions._score``, ``actions.Guard``, private names
# included, and a split whose whole claim is that nothing behaves differently
# may not open by breaking all of them.
#
# Generated from what those modules actually define. Adding a name over there
# and forgetting it here is the one mistake this file can still make on its
# own, which is why a test walks the four modules and checks.
# ruff: noqa: E402, F401
from matching import (BLOCKLIST, ERR_UNREACHABLE, LIST_LIMIT, _LEAD_FILLER,
                      _strip_lead_filler, LOCAL_CONFIDENT, _label,
                      _APOSTROPHES, _FOLD_MAP, _ALBUM_SEP, _ARTIST_SEP,
                      _NOT_AN_ARTIST, _fold, _normalize_apart)
from guard import (BLOCKED_SPEECH, NOT_OWNER_SPEECH, parse_blocklist,
                   is_blocked, ITEM_NAME_FIELDS, add_block, remove_block,
                   list_blocks, editing)
from transport import (VOLUME_STEP, pause, resume, next_track, previous_track,
                       change_volume, MAX_SLEEP_MINUTES, set_sleep,
                       cancel_sleep, now_playing, clear_queue, queue_list)
from library import (top_tracks_list, _LOCAL_KIND, _dispatch_play,
                     choose_from, choose_by_name, _LOCAL_KIND_RANK,
                     _local_group, library_candidates, best_match_score,
                     play_local, local_albums_list)
