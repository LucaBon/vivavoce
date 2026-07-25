"""Voice-action business logic, kept as pure functions for easy testing.

Each function takes an :class:`lms.LMSClient` (or any object with the same
methods) plus already-extracted slot values, performs the LMS/TIDAL operation,
and returns a speech string. The wording lives in the ``messages`` catalog
(referenced by key — see :mod:`messages` for the i18n plan); today the only
catalog is Italian. All LMS failures are turned into a friendly message
instead of raising, so the skill never crashes on a network hiccup.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, List, Optional

from blocklist_store import BlocklistStoreError
from lms import LMSError
from messages import msg

# Legacy alias, frozen in the default language at import: kept for external
# callers/tests; the code paths below call msg() so replies follow the
# per-request language.
ERR_UNREACHABLE = msg("err_unreachable")
VOLUME_STEP = 5
LIST_LIMIT = 5

# Fuzzy-match gating (see _score / _rank / play_song). Title scoring only *overrides*
# TIDAL's own relevance ranking for a clear EXACT title match (e.g. "Money" over
# "Money for Nothing"). For anything else — an artist-name or partial query, or
# padded junk titles that merely contain all the words — we trust TIDAL's ordering,
# which also weighs the artist/full text the bare song titles don't expose. Field
# testing showed title-only scoring can't tell a good partial match from padded
# junk, so we don't second-guess TIDAL with a "did you mean"; the spoken
# confirmation ("Riproduco X di Y") is the safety net instead.
# CONFIDENT_SCORE is used by tools/probe_lms.py to flag, in a dry run, whether any
# title strongly matches the query.
# The one exception to "trust TIDAL silently": a bare query that also matches an
# ARTIST name ("metti Beatrice" — the artist Beatrice Egli vs a song called
# Beatrice) is a real ambiguity the title scores can't see, so there we ask.
CONFIDENT_SCORE = 0.72
EXACT_SCORE = 0.98   # normalized-equal title -> override TIDAL and play this one
DIDYOUMEAN_LIMIT = 3  # read back at most the top 3 when asking "which one?"
# A name must match an artist at least this well before we treat the request as
# possibly meaning that artist. Whole-word containment ("beatrice" in "Beatrice
# Egli") scores 0.95, while multi-word song titles against unrelated artist
# names stay far below, so 0.9 catches bare names without firing on real titles.
ARTIST_ASK = 0.9
# How many search results to scan. TIDAL buries songs that share their TITLE
# with a popular artist's NAME deep under that artist's catalog (live check:
# 'Beatrice' by Sam Rivers sits at #27, Joe Henderson at #46, behind ~25
# Beatrice Egli/Dillon tracks), so 20 would miss every exact-title candidate.
SEARCH_DEPTH = 50


class ActionResult(str):
    """A speech string that also carries structured outcome data.

    Subclassing ``str`` keeps every existing caller and test working (equality,
    ``startswith``, ``.speak(...)``), while new callers can read ``.ok`` — did we
    act on the request? — and ``.candidates`` — a numbered list to disambiguate
    from. ``handle_many`` uses ``.ok`` instead of sniffing the ``"Non "`` prefix.
    """

    def __new__(cls, speech, *, ok=True, candidates=None, kind=None, terms=None,
                query=None):
        obj = super().__new__(cls, speech)
        obj.ok = ok
        obj.candidates = list(candidates or [])
        obj.kind = kind
        # Foreign names (title/artist/album/playlist) that appear verbatim in the
        # speech, so the web client can read those parts in their own language
        # while the Italian frame is read by an Italian voice.
        obj.terms = [t for t in (terms or []) if t]
        # The query a 'did you mean' asks about, so the router can remember
        # which answer the user picks (choice memory) keyed by this text.
        obj.query = query
        return obj


def _score(query: Optional[str], text: Optional[str]) -> float:
    """Similarity of a candidate ``text`` to the requested ``query`` in 0..1,
    accent/case-insensitive. Rewards the query's words all appearing in the
    candidate (so 'time' matches 'Time (Remastered)') and blends in a character
    ratio for near-misses/typos. Words are compared punctuation-free — spoken
    queries never carry it, titles do ('Beatrice (feat. Annalisa)' must contain
    'annalisa', not 'annalisa)')."""
    q = _normalize(query)
    t = _normalize(text)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    q_tokens = set(re.findall(r"\w+", q))
    t_tokens = set(re.findall(r"\w+", t))
    containment = len(q_tokens & t_tokens) / len(q_tokens) if q_tokens else 0.0
    ratio = difflib.SequenceMatcher(None, q, t).ratio()
    score = 0.6 * containment + 0.4 * ratio
    # Strong match when one side's words are wholly contained in the other: every
    # requested word is in the title ('time' -> 'Time (Remastered)'), OR the whole
    # title is in the request ('Comfortably Numb' <- 'comfortably numb pink floyd',
    # where the user appended the artist to disambiguate).
    if q_tokens and (q_tokens <= t_tokens or t_tokens <= q_tokens):
        score = max(score, 0.95)
    return score


def _rank(query: Optional[str], items: List[Dict], key: str = "title") -> List:
    """Return ``[(score, item), ...]`` sorted by descending match score against
    ``query``, keeping the original (TIDAL relevance) order as the tiebreaker."""
    scored = [(_score(query, it.get(key)), i, it) for i, it in enumerate(items)]
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [(sc, it) for sc, _i, it in scored]


# Leading filler the ASR/user often prepends ("metti la canzone X") that would
# pollute the search. Stripped before matching so "la canzone love" -> "love".
_LEAD_FILLER = re.compile(
    r"^(?:la\s+canzone|il\s+brano|la\s+traccia|il\s+pezzo|la\s+song|the\s+song)\s+",
    re.IGNORECASE,
)


def _strip_lead_filler(text: Optional[str]) -> str:
    return _LEAD_FILLER.sub("", (text or "").strip()).strip()


LOCAL_CONFIDENT = CONFIDENT_SCORE  # a local match must clearly fit the query to win


def _label(cand: Dict) -> str:
    """'Title di Artist' for a candidate, else just the title; an artist
    candidate reads as "l'artista Name"."""
    title = cand.get("title") or msg("generic_track")
    if cand.get("_kind") == "artist":
        return msg("label_artist", name=title)
    artist = cand.get("artist")
    return msg("label_title_artist", title=title, artist=artist) if artist else title


def _dedup_by_title_artist(cands: List[Dict]) -> List[Dict]:
    """Collapse candidates with the same (kind, title, artist) — several editions
    of the same recording shouldn't look like an ambiguous choice, but the song
    "Beatrice" and the artist "Beatrice" must stay two options."""
    seen = set()
    out = []
    for c in cands:
        key = (c.get("_kind"), _normalize(c.get("title")), _normalize(c.get("artist")))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _ndistinct_titles(cands: List[Dict]) -> int:
    return len({_normalize(c.get("title")) for c in cands})


# -- edition/version awareness ---------------------------------------------
# Marker words that distinguish EDITIONS of one recording rather than different
# songs ("Comfortably Numb" vs "Comfortably Numb (Live)"). Used two ways: to
# collapse such candidates into one song instead of a useless "did you mean",
# and to honor an explicitly requested edition ("metti comfortably numb live").
_VERSION_RE = re.compile(
    r"\b(?:live|remaster(?:ed|izzat[ao])?|remix(?:ed)?|acoustic|acustic[ao]|"
    r"unplugged|demo|instrumental|strumentale|karaoke|mono|stereo|deluxe|"
    r"extended|edit|single|version|versione|radio)\b",
    re.IGNORECASE,
)


def _version_terms(text: Optional[str]) -> frozenset:
    return frozenset(m.lower() for m in _VERSION_RE.findall(_normalize(text)))


def _version_base(text: Optional[str]) -> str:
    """The title with edition markers and their leftover punctuation removed:
    'comfortably numb (live) - remastered' -> 'comfortably numb'."""
    base = _VERSION_RE.sub(" ", _normalize(text))
    base = re.sub(r"[^\w\s]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def _version_pick(query: Optional[str], cands: List[Dict]) -> Optional[Dict]:
    """When ``cands`` are all editions of ONE song, the edition the query asks
    for (or the plain studio one when it names none); ``None`` when the
    candidates are genuinely different songs and asking is right."""
    if len({_version_base(c.get("title")) for c in cands}) != 1:
        return None
    want = _version_terms(query)

    def affinity(indexed):
        i, cand = indexed
        have = _version_terms(cand.get("title"))
        # Missing requested markers weigh most, unrequested extras next, the
        # service's own relevance order breaks ties.
        return (len(want - have), len(have - want), i)

    return min(enumerate(cands), key=affinity)[1]


def _did_you_mean(query: Optional[str], cands: List[Dict]) -> ActionResult:
    """Ask which of several candidates to play, reading back the top ones as
    '1: Title di Artist, ...'. ``cands`` are choose_from-ready (TIDAL {title,url}
    or local {title,action,arg}); callers pass an already blocked-filtered list."""
    picks = cands[:DIDYOUMEAN_LIMIT]
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=_label(c)) for i, c in enumerate(picks)
    )
    terms = []
    for c in picks:
        if c.get("title"):
            terms.append(c["title"])
        if c.get("artist"):
            terms.append(c["artist"])
    speech = msg("didyoumean", query=query, listing=listing)
    return ActionResult(speech, ok=True, candidates=picks, kind="disambiguate",
                        terms=terms, query=query)


def _artist_option(lms, query, tracks, exacts, *, guard=None) -> Optional[Dict]:
    """A choose_from-ready "l'artista Name" candidate when a bare query plausibly
    means an artist, else None. Gated on evidence already in hand — some returned
    track is BY an artist matching the query — before paying for the Artists
    lookup; a self-titled exact hit (the track "Madonna" by Madonna) already IS
    that artist, so it's not ambiguous. The artist's top tracks are resolved here,
    as plain URLs, so the later pick plays through any client the router passes."""

    def _hints(t):
        return _score(query, t.get("artist")) >= ARTIST_ASK

    if not any(_hints(t) for t in tracks) or any(_hints(t) for t in exacts):
        return None
    try:
        # First artist above threshold in the service's own relevance order —
        # NOT our best score: an obscure act named exactly "Beatrice" must not
        # shadow Beatrice Egli, and a bare "l'artista Beatrice" read-out
        # wouldn't even say which one it is.
        best = next(
            (c for c in lms.search_artists(query)
             if not (guard and guard.blocks(c.get("title")))
             and _score(query, c.get("title")) >= ARTIST_ASK),
            None,
        )
        if best is None:
            return None
        urls = [t["url"] for t in lms.artist_tracks(best["id"]) if t.get("url")]
    except LMSError:
        return None
    if not urls:
        return None
    return {"title": best["title"], "action": "play_urls", "arg": urls,
            "_kind": "artist"}


def _ask_song_or_artist(query, tracks, artist_opt, guard) -> ActionResult:
    """Ask "the song X (or Y) or the artist Z?" — up to two distinct songs plus
    the artist ('Beatrice' exists by Sam Rivers AND Joe Henderson besides the
    artist Beatrice Egli). Blocked songs drop out for restricted speakers (the
    artist option is already guard-filtered)."""
    picks = list(tracks)
    if guard and guard.restricted:
        picks = [t for t in picks if not is_blocked(t.get("title"), guard.blocklist)]
    picks = _dedup_by_title_artist(picks)[: DIDYOUMEAN_LIMIT - 1] + [artist_opt]
    return _did_you_mean(query, picks)


def _play_tidal_track(lms, track: Dict, fallback_title: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    if guard and guard.blocks(track.get("title")):
        return ActionResult(msg("blocked"), ok=False)
    lms.play_url(track["url"])
    speech, terms = _confirm_song(lms, track, fallback_title)
    return ActionResult(speech, ok=True, terms=terms)



# Spoken when a restricted (non-owner) speaker asks for a blocked song/singer.
BLOCKED_SPEECH = msg("blocked")
# Spoken when a non-owner tries to change the blocklist by voice.
NOT_OWNER_SPEECH = msg("not_owner")


def _normalize(text: Optional[str]) -> str:
    """Lowercase + strip accents + collapse spaces, for accent/case-insensitive
    Italian matching ('Andrà' -> 'andra')."""
    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


def parse_blocklist(raw) -> List[str]:
    """Turn a comma/newline string (or list) into de-duplicated display terms.

    Terms are kept in their original spoken/typed form (so they read back nicely
    in ``list_blocks``); matching normalizes on the fly in :func:`is_blocked`."""
    if not raw:
        return []
    parts = raw if isinstance(raw, (list, tuple)) else re.split(r"[,\n]", str(raw))
    out: List[str] = []
    seen = set()
    for part in parts:
        term = str(part).strip()
        norm = _normalize(term)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(term)
    return out


def is_blocked(text: Optional[str], blocklist: Optional[List[str]]) -> bool:
    """True if any blocklist term appears in ``text`` as a whole word (normalized).

    Word-boundary matching avoids false positives like a blocked 'ass' hitting
    'bass', while still catching multi-word terms and inflections around them."""
    norm = _normalize(text)
    if not norm:
        return False
    for term in blocklist or []:
        term_norm = _normalize(term)
        if term_norm and re.search(rf"\b{re.escape(term_norm)}\b", norm):
            return True
    return False


class Guard:
    """Speaker-based access gate. When ``restricted`` is True, any request text
    matching ``blocklist`` is refused with :data:`BLOCKED_SPEECH`. When it's
    False the guard is transparent, so passing ``guard=None`` is also a no-op."""

    def __init__(self, restricted: bool = False, blocklist: Optional[List[str]] = None):
        self.restricted = restricted
        self.blocklist = blocklist or []

    def blocks(self, *texts: Optional[str]) -> bool:
        if not self.restricted:
            return False
        return any(is_blocked(t, self.blocklist) for t in texts if t)

# Splits "titolo dall'album X" / "title from album X" into title + album.
_ALBUM_SEP = re.compile(
    r"\b(?:dall['’]?\s*album|dell['’]?\s*album|dal\s+disco|dall['’]?\s*disco|"
    r"from\s+(?:the\s+)?album)\b",
    re.IGNORECASE,
)
# Splits "titolo di/dei/degli X" / "title by X" into title + artist. Used only to
# *rank* results (the search still runs on the full text), so a mis-split — e.g. a
# title that itself contains "di" — degrades gracefully instead of breaking.
_ARTIST_SEP = re.compile(
    r"\b(?:dei|degli|delle|della|dell['’]|del|di|by)\s+", re.IGNORECASE
)


def parse_song_query(text: Optional[str]) -> Dict[str, Optional[str]]:
    """Parse a free-text song request into ``{'title', 'artist', 'album'}``.

    "Time dall'album Dark Side" -> title='Time', album='Dark Side'.
    "Comfortably Numb dei Pink Floyd" -> title='Comfortably Numb', artist='Pink Floyd'.
    "Comfortably Numb Pink Floyd" (no connector) stays title-only."""
    text = _strip_lead_filler(text)
    album = None
    match = _ALBUM_SEP.search(text)
    if match:
        pre = text[: match.start()].strip()
        album = text[match.end():].strip() or None
    else:
        pre = text
    title, artist = pre, None
    am = _ARTIST_SEP.search(pre)
    if am:
        head, tail = pre[: am.start()].strip(), pre[am.end():].strip()
        if head and tail:  # both sides non-empty -> treat as "title <conn> artist"
            title, artist = head, tail
    return {"title": title or None, "artist": artist, "album": album}


def play_song(lms, query: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    parsed = parse_song_query(query)
    title, artist, album = parsed["title"], parsed["artist"], parsed["album"]
    if not title and not album:
        return ActionResult(msg("ask_title"), ok=False)
    if guard and guard.blocks(title, artist, album):
        return ActionResult(msg("blocked"), ok=False)
    try:
        if album:
            return _play_from_album(lms, title, album, guard=guard)
        # Search on the full text (title + artist) — TIDAL's full-text search wants
        # both — then rank/disambiguate using the parsed parts.
        search_text = " ".join(p for p in (title, artist) if p) or title
        tracks = lms.search_tracks(search_text, count=SEARCH_DEPTH)
        if not tracks:
            return ActionResult(msg("no_track_found", title=title), ok=False)
        return _resolve_song(lms, tracks, title, artist, guard=guard)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)


def _resolve_song(lms, tracks, title, artist, *, guard=None) -> ActionResult:
    """Pick a track, disambiguate, or ask — from the TIDAL results and the parsed
    title/artist. Candidates stay in TIDAL's own relevance order, so padded-junk
    titles ranked low never reach the shortlist."""
    exacts = [t for t in tracks if _score(title, t.get("title")) >= EXACT_SCORE]
    strong = [t for t in tracks if _score(title, t.get("title")) >= CONFIDENT_SCORE]
    # 1) An artist was named -> play the matching edition (search_tracks carries the
    #    artist, so this picks the right one among identical-title songs).
    if artist and strong:
        best = max(strong[:DIDYOUMEAN_LIMIT], key=lambda t: _score(artist, t.get("artist")))
        if _score(artist, best.get("artist")) >= CONFIDENT_SCORE:
            return _play_tidal_track(lms, best, title, guard=guard)
    # Bare query: the name may mean an ARTIST rather than a title ("metti
    # Beatrice") — nothing else in the request disambiguates, so check.
    artist_opt = None if artist else _artist_option(lms, title, tracks, exacts, guard=guard)
    # 2) Exact title match -> play TIDAL's top exact (e.g. "Money" over "Money for
    #    Nothing") — unless the same name is also an artist -> ask which.
    # 3) No title match at all -> trust TIDAL's own ranking — unless the query
    #    matches an artist name -> ask between TIDAL's top song and the artist.
    if exacts:
        if artist_opt:
            return _ask_song_or_artist(title, exacts, artist_opt, guard)
        return _play_tidal_track(lms, exacts[0], title, guard=guard)
    if not strong:
        if artist_opt:
            return _ask_song_or_artist(title, tracks[:1], artist_opt, guard)
        return _play_tidal_track(lms, tracks[0], title, guard=guard)
    # 4) Several strong partial matches. One song (same title) -> play the top; if
    #    genuinely different titles -> ask the top 3. A matching artist joins the
    #    list either way.
    head = strong[:DIDYOUMEAN_LIMIT]
    if guard and guard.restricted:
        head = [t for t in head if not is_blocked(t.get("title"), guard.blocklist)]
    if not head:
        if artist_opt:
            return _did_you_mean(title, [artist_opt])
        return ActionResult(msg("no_track_found", title=title), ok=False)
    if _ndistinct_titles(head) < 2 and not artist_opt:
        return _play_tidal_track(lms, head[0], title, guard=guard)
    # Titles that differ only by edition markers ("X" vs "X (Live)") are ONE
    # song: pick the edition the request asks for instead of asking back.
    if not artist_opt:
        edition = _version_pick(title, head)
        if edition is not None:
            return _play_tidal_track(lms, edition, title, guard=guard)
    picks = _dedup_by_title_artist(head)
    if artist_opt:
        picks = picks[: DIDYOUMEAN_LIMIT - 1] + [artist_opt]
    if len(picks) < 2:
        return _play_tidal_track(lms, picks[0], title, guard=guard)
    return _did_you_mean(title, picks)


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
    lms, title: Optional[str], album: str, *, guard: Optional[Guard] = None
) -> ActionResult:
    result = lms.album_tracks(album)
    if not result["album"]:
        return ActionResult(msg("album_not_found", album=album), ok=False)
    album_name = result["album"]["title"] or album
    if guard and guard.blocks(album_name):
        return ActionResult(msg("blocked"), ok=False)
    if title:
        ranked = _rank(title, result["tracks"])
        if ranked and ranked[0][0] >= CONFIDENT_SCORE:
            track = ranked[0][1]
            if guard and guard.blocks(track.get("title")):
                return ActionResult(msg("blocked"), ok=False)
            lms.play_url(track["url"])
            return ActionResult(
                msg("playing_track_from_album", title=track["title"], album=album_name),
                ok=True, terms=[track["title"], album_name],
            )
        # title not found in that album -> play the whole album instead
        lms.play_browse_item(result["album"]["id"])
        return ActionResult(
            msg("track_not_in_album", title=title, album=album_name),
            ok=True, terms=[title, album_name],
        )
    lms.play_browse_item(result["album"]["id"])
    return ActionResult(
        msg("playing_album", album=album_name), ok=True, terms=[album_name]
    )


def play_album(lms, album: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    album = (album or "").strip()
    if not album:
        return ActionResult(msg("ask_album"), ok=False)
    if guard and guard.blocks(album):
        return ActionResult(msg("blocked"), ok=False)
    try:
        cands = lms.album_candidates(album)
        if not cands:
            return ActionResult(msg("album_not_found", album=album), ok=False)
        item = _rank(album, cands)[0][1]  # best title match, not blindly the first
        if guard and guard.blocks(item.get("title")):
            return ActionResult(msg("blocked"), ok=False)
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
        return ActionResult(msg("blocked"), ok=False)
    try:
        result = lms.artist_top_tracks(artist)
        if not result["artist"]:
            return ActionResult(msg("artist_not_found", artist=artist), ok=False)
        if guard and guard.blocks(result["artist"].get("title")):
            return ActionResult(msg("blocked"), ok=False)
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
        return ActionResult(msg("blocked"), ok=False)
    try:
        cands = lms.playlist_candidates(name)
        if not cands:
            return ActionResult(msg("playlist_not_found", name=name), ok=False)
        item = _rank(name, cands)[0][1]
        if guard and guard.blocks(item.get("title")):
            return ActionResult(msg("blocked"), ok=False)
        lms.play_browse_item(item["id"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_playlist", name=name), ok=True, terms=[name])


# -- queue semantics (add / play next / shuffle / repeat) -------------------
def _best_track(tracks: List[Dict], title, artist) -> Dict:
    """The single best track for a parsed query — same priorities as
    :func:`_resolve_song` (named artist > exact title > requested edition >
    service order) but never asks: queueing is low-stakes, a wrong guess is
    one 'salta' away and the confirmation says what was queued."""
    exacts = [t for t in tracks if _score(title, t.get("title")) >= EXACT_SCORE]
    strong = [t for t in tracks if _score(title, t.get("title")) >= CONFIDENT_SCORE]
    if artist and strong:
        best = max(strong[:DIDYOUMEAN_LIMIT],
                   key=lambda t: _score(artist, t.get("artist")))
        if _score(artist, best.get("artist")) >= CONFIDENT_SCORE:
            return best
    if exacts:
        return exacts[0]
    if strong:
        return _version_pick(title, strong[:DIDYOUMEAN_LIMIT]) or strong[0]
    return tracks[0]


def queue_song(lms, query: Optional[str], *, next_up: bool = False,
               guard: Optional[Guard] = None) -> ActionResult:
    """Add a song to the queue without touching what's playing — 'aggiungi X
    in coda' / 'play X next' (``next_up`` inserts right after the current
    track instead of appending)."""
    parsed = parse_song_query(query)
    title, artist = parsed["title"], parsed["artist"]
    if not title:
        return ActionResult(msg("ask_title"), ok=False)
    if guard and guard.blocks(title, artist):
        return ActionResult(msg("blocked"), ok=False)
    try:
        search_text = " ".join(p for p in (title, artist) if p)
        tracks = lms.search_tracks(search_text, count=SEARCH_DEPTH)
        if not tracks:
            return ActionResult(msg("no_track_found", title=title), ok=False)
        track = _best_track(tracks, title, artist)
        if guard and guard.blocks(track.get("title")):
            return ActionResult(msg("blocked"), ok=False)
        if next_up:
            lms.insert_url(track["url"])
        else:
            lms.add_url(track["url"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    name = track.get("title") or title
    key = "queued_next" if next_up else "queued"
    return ActionResult(msg(key, name=name), ok=True, terms=[name])


def queue_local(lms, query: Optional[str], *, next_up: bool = False,
                guard: Optional[Guard] = None) -> ActionResult:
    """Queue a LIBRARY track ('aggiungi X in coda' with the local source).
    Only a confident title match queues — a loose hit must fall through to
    the streaming search, like :func:`play_local` does for plays."""
    parsed = parse_song_query(query)
    title, artist = parsed["title"], parsed["artist"]
    if not title:
        return ActionResult(msg("ask_title"), ok=False)
    if guard and guard.blocks(title, artist):
        return ActionResult(msg("blocked"), ok=False)
    try:
        cands = lms.local_track_candidates(title)
        ranked = [(s, c) for s, c in _rank(title, cands) if s >= LOCAL_CONFIDENT]
        if artist:
            by_artist = [(s, c) for s, c in ranked
                         if _score(artist, c.get("artist")) >= CONFIDENT_SCORE]
            ranked = by_artist or ranked
        if not ranked:
            return ActionResult(msg("local_not_found", query=title), ok=False)
        track = ranked[0][1]
        if guard and guard.blocks(track.get("title")):
            return ActionResult(msg("blocked"), ok=False)
        lms.add_local_track(track["id"], next_up=next_up)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    name = track.get("title") or title
    key = "queued_next" if next_up else "queued"
    return ActionResult(msg(key, name=name), ok=True, terms=[name])


def set_shuffle(lms, on: bool) -> ActionResult:
    try:
        lms.set_shuffle(1 if on else 0)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("shuffle_on" if on else "shuffle_off"), ok=True)


def set_repeat(lms, on: bool) -> ActionResult:
    try:
        lms.set_repeat(2 if on else 0)  # 2 = repeat the whole queue
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("repeat_on" if on else "repeat_off"), ok=True)


def pause(lms) -> ActionResult:
    try:
        lms.pause()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("paused"), ok=True)


def resume(lms) -> ActionResult:
    try:
        lms.resume()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("resumed"), ok=True)


def next_track(lms) -> ActionResult:
    try:
        lms.next_track()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("next_track"), ok=True)


def previous_track(lms) -> ActionResult:
    try:
        lms.previous_track()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("previous_track"), ok=True)


def change_volume(lms, direction: str) -> ActionResult:
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
    delta = VOLUME_STEP if direction == "up" else -VOLUME_STEP
    try:
        lms.volume(delta)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("volume_up" if direction == "up" else "volume_down"),
                        ok=True)


def set_sleep(lms, minutes: int) -> ActionResult:
    """Arm the LMS sleep timer: playback stops after ``minutes``."""
    if not minutes or minutes <= 0:
        return ActionResult(msg("ask_sleep"), ok=False)
    try:
        lms.sleep(int(minutes) * 60)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("sleep_set", minutes=int(minutes)), ok=True)


def cancel_sleep(lms) -> ActionResult:
    try:
        lms.sleep(0)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("sleep_cancelled"), ok=True)


def now_playing(lms) -> str:
    try:
        info = lms.now_playing_info()
    except LMSError:
        return msg("err_unreachable")
    if not info or not info.get("title"):
        return ActionResult(msg("nothing_playing"), ok=True)
    title = info.get("title")
    artist = info.get("artist")
    if artist:
        return ActionResult(
            msg("now_playing_by", title=title, artist=artist),
            ok=True, terms=[title, artist],
        )
    return ActionResult(msg("now_playing", title=title), ok=True, terms=[title])


# -- conversational flow: list -> choose by number ------------------------
def top_tracks_list(
    lms, artist: Optional[str], limit: int = LIST_LIMIT, *, guard: Optional[Guard] = None
) -> Dict:
    """Return ``{'speech', 'candidates'}``. The handler reads the list aloud and
    stores ``candidates`` (title+url) in session for a follow-up choice."""
    artist = (artist or "").strip()
    if not artist:
        return {"speech": msg("which_artist"), "candidates": []}
    if guard and guard.blocks(artist):
        return {"speech": msg("blocked"), "candidates": []}
    try:
        tracks = lms.artist_top_tracks(artist)["tracks"]
    except LMSError:
        return {"speech": msg("err_unreachable"), "candidates": []}
    if guard and guard.restricted:  # drop blocked tracks so they can't be chosen
        tracks = [t for t in tracks if not is_blocked(t.get("title"), guard.blocklist)]
    tracks = tracks[:limit]
    if not tracks:
        return {"speech": msg("no_tracks_for", artist=artist), "candidates": []}
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=t["title"]) for i, t in enumerate(tracks)
    )
    speech = msg("top_tracks", artist=artist, listing=listing)
    candidates = [{"title": t["title"], "url": t["url"]} for t in tracks]
    return {"speech": speech, "candidates": candidates}


def _dispatch_play(lms, candidate: Dict) -> None:
    """Play a candidate. Its 'action'/'arg' say how; falls back to a plain URL
    so both TIDAL ({'title','url'}) and local ({'title','action','arg'}) lists work."""
    action = candidate.get("action")
    arg = candidate.get("arg")
    if action == "play_album_id":
        lms.play_local_album(arg)
    elif action == "play_artist_id":
        lms.play_local_artist(arg)
    elif action == "play_track_id":
        lms.play_local_track(arg)
    elif action == "play_urls":  # streaming artist pick: pre-resolved top tracks
        lms.play_tracks(arg)
    else:
        lms.play_url(arg or candidate.get("url"))


def choose_from(
    lms,
    candidates: Optional[List[Dict]],
    number: Optional[int],
    *,
    guard: Optional[Guard] = None,
) -> str:
    """Play the N-th candidate from a previously read-out list."""
    if not candidates:
        return msg("no_open_list")
    if number is None or number < 1 or number > len(candidates):
        return msg("pick_range", n=len(candidates))
    chosen = candidates[number - 1]
    if guard and guard.blocks(chosen.get("title")):
        return msg("blocked")
    try:
        _dispatch_play(lms, chosen)
    except LMSError:
        return msg("err_unreachable")
    return ActionResult(
        msg("playing", name=chosen["title"]), ok=True, terms=[chosen["title"]]
    )


def choose_by_name(
    lms,
    candidates: Optional[List[Dict]],
    name: Optional[str],
    *,
    guard: Optional[Guard] = None,
) -> Optional[str]:
    """Play the candidate whose title matches ``name`` from a previously read-out
    list. Returns ``None`` when there's no list, no name, or no title matches, so
    the caller falls back to a fresh search. ``None`` is deliberately *not* a
    'Non ...' miss string: it means 'this wasn't a selection, keep routing'."""
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
    if guard and guard.blocks(chosen.get("title")):
        return msg("blocked")
    try:
        _dispatch_play(lms, chosen)
    except LMSError:
        return msg("err_unreachable")
    return ActionResult(
        msg("playing", name=chosen["title"]), ok=True, terms=[chosen["title"]]
    )


# -- local library (Music Folder / USB) -----------------------------------
def _local_group(cands, query, kind, action, guard):
    """Confident, distinct candidates for one category, each scored by its own name
    (album/track by title, artist by name) and turned into a choose_from-ready dict."""
    out = []
    for c in cands:
        if guard and guard.restricted and is_blocked(c.get("title"), guard.blocklist):
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


def play_local(lms, query: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    """Play from the local library. Candidates are scored (title, or artist name for
    the artist category) so a generic word like 'love' never plays an unrelated row;
    an artist query plays the artist, not one of their albums; and when several
    tracks genuinely match, it asks (local rows carry the artist, so the list reads
    'Love di X, Love di Y'). A near-perfect hit in a second category also asks —
    the track "Beatrice" vs the artist Beatrice Egli."""
    query = _strip_lead_filler(query)
    if not query:
        return ActionResult(msg("ask_query"), ok=False)
    if guard and guard.blocks(query):
        return ActionResult(msg("blocked"), ok=False)
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
        groups.sort(key=lambda g: -g[0][0])  # best-scoring category wins
        picks = [cand for _s, cand in groups[0]]
        # A near-perfect hit in another category is a real ambiguity too — the
        # track "Beatrice" vs the ARTIST Beatrice Egli — so offer its best row.
        for other in groups[1:]:
            score, cand = other[0]
            if score >= ARTIST_ASK:
                picks.append(cand)
        distinct = _dedup_by_title_artist(picks)
        if len(distinct) >= 2:
            return _did_you_mean(query, distinct)
        item = distinct[0]
        _dispatch_play(lms, item)
        speech = (
            msg("playing_local_album", title=item["title"])
            if item["_kind"] == "album"
            else msg("playing_local", title=item["title"])
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
        return {"speech": msg("which_artist"), "candidates": []}
    if guard and guard.blocks(artist):
        return {"speech": msg("blocked"), "candidates": []}
    try:
        result = lms.local_albums_by_artist(artist)
    except LMSError:
        return {"speech": msg("err_unreachable"), "candidates": []}
    if not result["artist"]:
        return {"speech": msg("local_no_artist", artist=artist), "candidates": []}
    albums = result["albums"]
    if guard and guard.restricted:  # drop blocked albums so they can't be chosen
        albums = [a for a in albums if not is_blocked(a.get("title"), guard.blocklist)]
    albums = albums[:limit]
    if not albums:
        return {"speech": msg("local_no_albums", artist=artist), "candidates": []}
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=a["title"]) for i, a in enumerate(albums)
    )
    speech = msg("local_albums", artist=result["artist"]["title"], listing=listing)
    candidates = [
        {"title": a["title"], "action": "play_album_id", "arg": a["id"]} for a in albums
    ]
    return {"speech": speech, "candidates": candidates}


# -- genre / era (local library) -------------------------------------------
# "metti del jazz" / "play some jazz": the partitive is filler, the genre name
# is what's left. Stripped before matching against the library's genre list.
_GENRE_FILLER = re.compile(
    r"^(?:un\s+po'?\s+(?:di|del|dello|della)|del|dello|della|dei|degli|delle|"
    r"some)\s+",
    re.IGNORECASE,
)


def play_genre(lms, query: Optional[str], *, guard: Optional[Guard] = None) -> ActionResult:
    """Play a library GENRE shuffled ("metti del jazz") — something a cloud
    assistant can't do on a personal collection. Returns a miss (``ok=False``)
    when no genre matches confidently, so the router falls through to the
    normal song search: this never steals real title queries."""
    query = _GENRE_FILLER.sub("", _strip_lead_filler(query)).strip()
    if not query:
        return ActionResult(msg("ask_query"), ok=False)
    if guard and guard.blocks(query):
        return ActionResult(msg("blocked"), ok=False)
    # Stricter than _score on purpose: every requested word must be in the
    # genre NAME ("rock" -> Rock, "rock and roll" -> Rock & Roll), never the
    # reverse — the genre "Rock" must not swallow the title query "Rock DJ".
    q_norm = _normalize(query)
    q_tokens = set(re.findall(r"\w+", q_norm))
    try:
        matches = []
        for cand in lms.local_genre_candidates(query):
            t_norm = _normalize(cand.get("title"))
            t_tokens = set(re.findall(r"\w+", t_norm))
            if not t_tokens or not q_tokens:
                continue
            if q_norm == t_norm:
                matches.append((0, len(t_tokens), cand))
            elif q_tokens <= t_tokens:
                matches.append((1, len(t_tokens), cand))
        if not matches:
            return ActionResult(msg("local_not_found", query=query), ok=False)
        matches.sort(key=lambda m: (m[0], m[1]))
        genre = matches[0][2]
        lms.play_local_genre(genre["id"])
        lms.set_shuffle(1)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    name = genre["title"] or query
    return ActionResult(msg("playing_genre", genre=name), ok=True, terms=[name])


def play_decade(lms, decade: int, *, guard: Optional[Guard] = None) -> ActionResult:
    """Play the library's music from one decade shuffled ("musica anni 80").
    ``decade`` is the starting year (1980). Only years actually present in the
    library are queued; none -> honest miss."""
    label = f"{decade % 100:02d}" if decade < 2000 else str(decade)
    try:
        years = sorted(y for y in lms.local_years() if decade <= y < decade + 10)
        if not years:
            return ActionResult(msg("no_decade_music", decade=label), ok=False)
        lms.play_local_years(years)
        lms.set_shuffle(1)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_decade", decade=label), ok=True)


# -- "more like this" (streaming artist mix / radio) ------------------------
def play_similar(lms, *, guard: Optional[Guard] = None) -> ActionResult:
    """Play music similar to the current track: the streaming service's
    'Artist Mix'/radio node for the now-playing artist, falling back to that
    artist's top tracks when the service has no mix node."""
    try:
        info = lms.now_playing_info()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    artist = (info or {}).get("artist")
    if not artist:
        return ActionResult(msg("similar_no_current"), ok=False)
    if guard and guard.blocks(artist):
        return ActionResult(msg("blocked"), ok=False)
    try:
        node = lms.find_artist(artist)
        if node:
            mix = lms.artist_mix_node(node["id"])
            if mix:
                lms.play_browse_item(mix)
                return ActionResult(msg("playing_similar", artist=artist),
                                    ok=True, terms=[artist])
            urls = [t["url"] for t in lms.artist_tracks(node["id"]) if t.get("url")]
            if urls:
                lms.play_tracks(urls)
                return ActionResult(msg("playing_similar", artist=artist),
                                    ok=True, terms=[artist])
        return ActionResult(msg("artist_unplayable", artist=artist), ok=False)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)


# -- voice-editable blocklist (owner only) --------------------------------
# These edit only the *dynamic* stored terms; the config KIDSAFE_BLOCKLIST
# baseline is permanent and can't be removed by voice.
def add_block(store, term: Optional[str], *, is_owner: bool) -> str:
    """Add a song/singer term to the blocklist. Owner-gated."""
    if not is_owner:
        return msg("not_owner")
    term = (term or "").strip()
    if not term:
        return msg("ask_block")
    try:
        terms = store.get()
        if any(_normalize(t) == _normalize(term) for t in terms):
            return msg("already_blocked", term=term)
        store.put(terms + [term])
    except BlocklistStoreError:
        return msg("blocklist_save_error")
    return msg("block_added", term=term)


def remove_block(store, term: Optional[str], *, is_owner: bool) -> str:
    """Remove a term from the blocklist. Owner-gated."""
    if not is_owner:
        return msg("not_owner")
    term = (term or "").strip()
    if not term:
        return msg("ask_unblock")
    try:
        terms = store.get()
        kept = [t for t in terms if _normalize(t) != _normalize(term)]
        if len(kept) == len(terms):
            return msg("not_in_blocklist", term=term)
        store.put(kept)
    except BlocklistStoreError:
        return msg("blocklist_update_error")
    return msg("block_removed", term=term)


def list_blocks(store, *, is_owner: bool) -> str:
    """Read the blocked terms aloud. Owner-gated."""
    if not is_owner:
        return msg("not_owner")
    terms = store.get()
    if not terms:
        return msg("blocklist_empty")
    return msg("blocklist_listing", terms=", ".join(terms))
