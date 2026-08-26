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
CONFIDENT_SCORE = 0.72
EXACT_SCORE = 0.98   # normalized-equal title -> override TIDAL and play this one
DIDYOUMEAN_LIMIT = 3  # read back at most the top 3 when asking "which one?"

# mode ("play"/"add"/"insert" — see play_song) -> the message-key suffix/name
# it maps to. Shared by every place that acts on a resolved song/album so the
# mapping is defined once instead of duplicated per call site.
_MODE_SUFFIX = {"play": "", "add": "_queued", "insert": "_queued_next"}
_MODE_KEY = {"play": "playing", "add": "queued", "insert": "queued_next"}
_MODE_KEY_BY = {"add": "queued_by", "insert": "queued_next_by"}


class ActionResult(str):
    """A speech string that also carries structured outcome data.

    Subclassing ``str`` keeps every existing caller and test working (equality,
    ``startswith``, ``.speak(...)``), while new callers can read ``.ok`` — did we
    act on the request? — and ``.candidates`` — a numbered list to disambiguate
    from. ``handle_many`` uses ``.ok`` instead of sniffing the ``"Non "`` prefix.
    """

    def __new__(cls, speech, *, ok=True, candidates=None, kind=None, terms=None):
        obj = super().__new__(cls, speech)
        obj.ok = ok
        obj.candidates = list(candidates or [])
        obj.kind = kind
        # Foreign names (title/artist/album/playlist) that appear verbatim in the
        # speech, so the web client can read those parts in their own language
        # while the Italian frame is read by an Italian voice.
        obj.terms = [t for t in (terms or []) if t]
        return obj


def _score(query: Optional[str], text: Optional[str], *,
           subset_floor: bool = True) -> float:
    """Similarity of a candidate ``text`` to the requested ``query`` in 0..1,
    accent/case-insensitive. Rewards the query's words all appearing in the
    candidate (so 'time' matches 'Time (Remastered)') and blends in a character
    ratio for near-misses/typos.

    ``subset_floor=False`` turns off the 0.95 shortcut below. The floor answers
    "does this candidate satisfy the request?", and for that it is right — but
    it saturates, and a saturated score cannot rank two *phrasings* of the same
    request against each other. Every phrase whose words merely contain a title
    lands on the same 0.95: «bollicine in cucina» against *Bollicine* and
    «musica rilassante in cucina» against an album called *Cucina* are
    indistinguishable with the floor on, and tell the two apart cleanly with it
    off (0.457 against 0.295). The room gate in ``pro/multiroom.py`` is the one
    caller that needs to compare phrasings; everything else wants the floor and
    gets it by default.
    """
    q = _normalize(query)
    t = _normalize(text)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    q_tokens = set(q.split())
    t_tokens = set(t.split())
    containment = len(q_tokens & t_tokens) / len(q_tokens) if q_tokens else 0.0
    ratio = difflib.SequenceMatcher(None, q, t).ratio()
    score = 0.6 * containment + 0.4 * ratio
    # Strong match when one side's words are wholly contained in the other: every
    # requested word is in the title ('time' -> 'Time (Remastered)'), OR the whole
    # title is in the request ('Comfortably Numb' <- 'comfortably numb pink floyd',
    # where the user appended the artist to disambiguate).
    if subset_floor and q_tokens and (q_tokens <= t_tokens or t_tokens <= q_tokens):
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
    """'Title di Artist' for a candidate, else just the title."""
    title = cand.get("title") or msg("generic_track")
    artist = cand.get("artist")
    return msg("label_title_artist", title=title, artist=artist) if artist else title


def _dedup_by_title_artist(cands: List[Dict]) -> List[Dict]:
    """Collapse candidates with the same (title, artist) — several editions of the
    same recording shouldn't look like an ambiguous choice."""
    seen = set()
    out = []
    for c in cands:
        key = (_normalize(c.get("title")), _normalize(c.get("artist")))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _ndistinct_titles(cands: List[Dict]) -> int:
    return len({_normalize(c.get("title")) for c in cands})


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
    return ActionResult(speech, ok=True, candidates=picks, kind="disambiguate", terms=terms)


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
        return ActionResult(msg("blocked"), ok=False)
    if mode == "play":
        lms.play_url(track["url"])
        speech, terms = _confirm_song(lms, track, fallback_title)
        # _confirm_song may have LEARNED the artist from the now-playing
        # status: TIDAL song-search items don't always carry one, and a
        # blocked artist discovered a moment late must still not play — and
        # certainly must not be read aloud in the confirmation.
        if guard and guard.blocks(*terms):
            _undo_play(lms)
            return ActionResult(msg("blocked"), ok=False)
        return ActionResult(speech, ok=True, terms=terms)
    getattr(lms, f"{mode}_url")(track["url"])
    name = track.get("title") or fallback_title
    artist = track.get("artist")
    if not artist:
        return ActionResult(msg(_MODE_KEY[mode], name=name), ok=True, terms=[name])
    return ActionResult(msg(_MODE_KEY_BY[mode], name=name, artist=artist),
                        ok=True, terms=[name, artist])



# Spoken when a restricted (non-owner) speaker asks for a blocked song/singer.
BLOCKED_SPEECH = msg("blocked")
# Spoken when a non-owner tries to change the blocklist by voice.
NOT_OWNER_SPEECH = msg("not_owner")


# Apostrophes in every shape a title, a keyboard or a recogniser produces.
# They are DELETED rather than turned into a space: Italian is full of
# l'/dell'/nell', and splitting "l'amore" into two tokens would match every
# title containing a bare "l". The practical case is the other direction —
# Web Speech drops the apostrophe entirely, so «dont stop me now» has to
# reach "Don't Stop Me Now".
_APOSTROPHES = "'\u2019\u02bc\u2018\u00b4`"

# Letters that carry no combining mark to strip: NFKD leaves them whole, so a
# small table is the only way «Motörhead» stays fine while "Straße" and
# "Sigur Rós"-style Nordic spellings still fold to what a recogniser writes.
_FOLD_MAP = {
    "\u00df": "ss", "\u00f8": "o", "\u00e6": "ae", "\u0153": "oe",
    "\u0142": "l", "\u0111": "d", "\u00f0": "d", "\u00fe": "th",
    "\u0131": "i", "\u0127": "h", "\u014b": "n",
}


def _normalize(text: Optional[str]) -> str:
    """Lowercase, fold accents and punctuation, collapse spaces.

    Punctuation used to survive this, and it decided matches: "Another Brick
    in the Wall, Pt. 1" scored 0.089 against «wall» because the comma and the
    full stop welded themselves to their neighbours, and "Don't Stop Me Now"
    scored 0.84 against the apostrophe-less «dont stop me now» — enough to
    ask "which one?" instead of playing it. Anything that isn't a letter or a
    digit is a separator now (``isalnum`` rather than an ASCII class, so
    Cyrillic/Greek/CJK titles keep their characters), and apostrophes vanish.
    """
    lowered = "".join(_FOLD_MAP.get(c, c) for c in (text or "").lower())
    decomposed = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    stripped = "".join(c for c in stripped if c not in _APOSTROPHES)
    spaced = "".join(c if c.isalnum() else " " for c in stripped)
    return re.sub(r"\s+", " ", spaced).strip()


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


# Every field of a resolved item that names something a blocklist term could
# be about. Checking only ``title`` was the hole: with ["Eminem"] blocked, a
# child asking «metti Lose Yourself» never says the blocked word, so the
# request text passed — and the track played, artist read aloud.
ITEM_NAME_FIELDS = ("title", "artist", "album", "name")


def is_blocked_item(item: Optional[Dict], blocklist: Optional[List[str]]) -> bool:
    """True if any blocklist term matches ANY name field of a resolved item."""
    if not item:
        return False
    return any(is_blocked(item.get(f), blocklist) for f in ITEM_NAME_FIELDS)


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

    def blocks_item(self, item: Optional[Dict]) -> bool:
        """The single choke point for a *resolved* item (a track, album,
        artist or favourite dict): checks every name field, not just the
        title. Use this everywhere something is about to be played, queued or
        read aloud — the request text alone never sees the artist."""
        if not self.restricted:
            return False
        return is_blocked_item(item, self.blocklist)

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

# Tails that are never an artist name — the phrase just happens to contain a
# connector. Without this, "Ti amo di più" searched for a singer called
# «più», and "Stand By Me" for one called "Me".
_NOT_AN_ARTIST = {
    "piu", "meno", "me", "te", "noi", "voi", "lui", "lei", "loro", "se",
    "you", "us", "it", "her", "him", "them", "myself", "yourself", "now",
    "here", "there", "one", "two", "all", "more", "less", "everyone",
}


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
    # Stripping the lead filler can leave the connector in front («la canzone
    # di Marinella di De André» -> "di Marinella di De André"): drop it, or it
    # becomes part of the title and drags every score down.
    lead = _ARTIST_SEP.match(pre)
    if lead and pre[lead.end():].strip():
        pre = pre[lead.end():].strip()
    title, artist = pre, None
    # The LAST connector, not the first: "Stand By Me by Ben E. King" split on
    # its own "By" and searched for a song called "Stand". Scanned right to
    # left so a title that itself contains a connector keeps it, and skipped
    # entirely when the tail is a word no artist is called.
    for am in reversed(list(_ARTIST_SEP.finditer(pre))):
        head, tail = pre[: am.start()].strip(), pre[am.end():].strip()
        if not head or not tail:
            continue
        if _normalize(tail) in _NOT_AN_ARTIST:
            continue
        title, artist = head, tail
        break
    return {"title": title or None, "artist": artist, "album": album}


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
        return ActionResult(msg("blocked"), ok=False)
    try:
        if album:
            return _play_from_album(lms, title, album, mode=mode, guard=guard)
        # Search on the full text (title + artist) — TIDAL's full-text search wants
        # both — then rank/disambiguate using the parsed parts.
        search_text = " ".join(p for p in (title, artist) if p) or title
        tracks = lms.search_tracks(search_text)
        if not tracks:
            return ActionResult(msg("no_track_found", title=title), ok=False)
        return _resolve_song(lms, tracks, title, artist, mode=mode, guard=guard)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)


def _resolve_song(lms, tracks, title, artist, *, mode: str = "play", guard=None) -> ActionResult:
    """Pick a track, disambiguate, or ask — from the TIDAL results and the parsed
    title/artist. Candidates stay in TIDAL's own relevance order, so padded-junk
    titles ranked low never reach the shortlist."""
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
        return ActionResult(msg("blocked"), ok=False)
    suffix = _MODE_SUFFIX[mode]
    if title:
        ranked = _rank(title, result["tracks"])
        if ranked and ranked[0][0] >= CONFIDENT_SCORE:
            track = ranked[0][1]
            if guard and guard.blocks_item(track):
                return ActionResult(msg("blocked"), ok=False)
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
        return ActionResult(msg("blocked"), ok=False)
    try:
        cands = lms.album_candidates(album)
        if not cands:
            return ActionResult(msg("album_not_found", album=album), ok=False)
        item = _rank(album, cands)[0][1]  # best title match, not blindly the first
        if guard and guard.blocks_item(item):
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
        if guard and guard.blocks_item(result["artist"]):
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
        if guard and guard.blocks_item(item):
            return ActionResult(msg("blocked"), ok=False)
        lms.play_browse_item(item["id"])
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("playing_playlist", name=name), ok=True, terms=[name])


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


# A sleep timer beyond half a day is a misheard number, not a request
# («spegni tra 100000 minuti» was armed as-is).
MAX_SLEEP_MINUTES = 12 * 60


def set_sleep(lms, minutes: int) -> ActionResult:
    """Arm the LMS sleep timer: playback stops after ``minutes``."""
    if not minutes or minutes <= 0:
        return ActionResult(msg("ask_sleep"), ok=False)
    minutes = int(minutes)
    if minutes > MAX_SLEEP_MINUTES:
        return ActionResult(msg("sleep_too_long", max=MAX_SLEEP_MINUTES),
                            ok=False)
    try:
        lms.sleep(minutes * 60)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    key = "sleep_set_one" if minutes == 1 else "sleep_set"
    return ActionResult(msg(key, minutes=minutes), ok=True)


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
    # "status - 1" hands back the queue head whatever the transport is doing,
    # so a stopped player used to answer "Sta suonando X" about a song nobody
    # could hear. Paused says paused; stopped says nothing is playing. Only an
    # explicit mode contradicts the queue head — a transport that reports none
    # is taken at face value, as before.
    mode = info.get("mode")
    if mode == "stop":
        return ActionResult(msg("nothing_playing"), ok=True)
    prefix = "paused_on" if mode == "pause" else "now_playing"
    title = info.get("title")
    artist = info.get("artist")
    if artist:
        return ActionResult(
            msg(prefix + "_by", title=title, artist=artist),
            ok=True, terms=[title, artist],
        )
    return ActionResult(msg(prefix, title=title), ok=True, terms=[title])


# -- queue (playlist) management -------------------------------------------
def clear_queue(lms) -> ActionResult:
    try:
        lms.clear_queue()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("queue_cleared"), ok=True)


def queue_list(lms, limit: int = LIST_LIMIT, *, guard: Optional[Guard] = None) -> ActionResult:
    """Read back the next few tracks queued after the current one."""
    try:
        upcoming = lms.queue_upcoming(limit)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    if guard and guard.restricted:  # never read a blocked title back aloud
        upcoming = [t for t in upcoming if not is_blocked_item(t, guard.blocklist)]
    if not upcoming:
        return ActionResult(msg("queue_empty"), ok=True)
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=_label(t)) for i, t in enumerate(upcoming)
    )
    terms = [t["title"] for t in upcoming] + [t["artist"] for t in upcoming if t.get("artist")]
    return ActionResult(msg("queue_list", listing=listing), ok=True, terms=terms)


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
        return ActionResult(msg("blocked"), ok=False)
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
        tracks = [t for t in tracks if not is_blocked_item(t, guard.blocklist)]
    tracks = tracks[:limit]
    if not tracks:
        return {"speech": msg("no_tracks_for", artist=artist), "candidates": []}
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=t["title"]) for i, t in enumerate(tracks)
    )
    speech = msg("top_tracks", artist=artist, listing=listing)
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
) -> str:
    """Act on the N-th candidate from a previously read-out list (mode: see
    :func:`play_song`)."""
    if not candidates:
        return msg("no_open_list")
    if number is None or number < 1 or number > len(candidates):
        return msg("pick_range", n=len(candidates))
    chosen = candidates[number - 1]
    if guard and guard.blocks_item(chosen):
        return msg("blocked")
    try:
        _dispatch_play(lms, chosen, mode=mode)
    except LMSError:
        return msg("err_unreachable")
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
) -> Optional[str]:
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
        return msg("blocked")
    try:
        _dispatch_play(lms, chosen, mode=mode)
    except LMSError:
        return msg("err_unreachable")
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
    routing, and the refusal («c'è, ma non è adatta alla tua età») confirms the
    record is in the house where the answer it replaced leaked nothing.
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
        albums = [a for a in albums if not is_blocked_item(a, guard.blocklist)]
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
