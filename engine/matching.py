"""Turning what was said into a candidate, and into words again.

The shared vocabulary of the engine: how close a candidate is to the request
(:func:`_score`), how a request is broken into title/artist/album
(:func:`parse_song_query`), how text is normalised before any of that, and the
:class:`ActionResult` every action hands back. It knows nothing about players,
libraries or licences — it is all text in, numbers and strings out, which is
why the modules that *do* act can all depend on it and none of them on each
other.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, List, Optional

from messages import msg

# Legacy alias, frozen in the default language at import: kept for external
# callers/tests; the code paths below call msg() so replies follow the
# per-request language.
ERR_UNREACHABLE = msg("err_unreachable")

# How many rows a list read out loud may carry. Any longer and nobody
# remembers the first one by the time the last is spoken.
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


# ``kind`` values that mean something to the dispatch, not just to bookkeeping.
#
# GATE marks a refusal the words cannot argue with: no Pro licence, not the
# owner, blocked for this listener. It answers a question about *who is asking*
# and what they hold, never about what was heard — which is why ``handle_many``
# must stop trying speech-recognition alternatives when it sees one. Retrying
# is not merely pointless (a second transcription does not buy a licence): an
# alternative that mangles the room name, or the blocked artist, misses the
# gate entirely and routes somewhere that *acts*. A free listener asking for
# music in the front room heard it start in the kitchen instead of the pitch,
# and a child could re-roll the dice until one alternative slipped past.
#
# It is also, being a truthy ``kind``, invisible to ``Router._tag`` — which is
# right on its own terms: a refusal is not a play to hang a source or a room on.
GATE = "gate"

# A blocklist reply is about the whole house — the store behind it is global —
# so ``Router._tag`` must not splice a room into it. «Ok, ho bloccato Eminem in
# Salotto» describes a per-room blocklist that does not exist, and the read-out
# was worse: «Brani bloccati: Eminem in Salotto» reads as a blocked *term*.
BLOCKLIST = "blocklist"


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


def _fold(text: Optional[str]) -> str:
    """Lowercase and strip every accent/ligature, leaving punctuation alone."""
    lowered = "".join(_FOLD_MAP.get(c, c) for c in (text or "").lower())
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


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
    stripped = "".join(c for c in _fold(text) if c not in _APOSTROPHES)
    spaced = "".join(c if c.isalnum() else " " for c in stripped)
    return re.sub(r"\s+", " ", spaced).strip()


def _normalize_apart(text: Optional[str]) -> str:
    """:func:`_normalize`, but the apostrophe separates instead of vanishing.

    Deleting it is right for *scoring* — it is what lets «dont stop me now»
    reach "Don't Stop Me Now" — and wrong for anything that needs a word
    boundary, because it welds the term to its neighbour: ``\bestasi\b`` stops
    matching "L'Estasi dell'Oro" and ``\beminem\b`` stops matching "Eminem's
    Greatest Hits". Elision makes that the common case in Italian, not the
    exotic one. Callers that match on word boundaries check this form too.
    """
    spaced = "".join(c if c.isalnum() else " " for c in _fold(text))
    return re.sub(r"\s+", " ", spaced).strip()


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
