"""Vague requests — the half of them that was never a machine-learning problem.

«metti qualcosa di rilassante» has no title in it, so the deterministic parser
rejects it by construction: it looks for a song called "qualcosa di rilassante",
finds nothing, and says so. That is the right answer to the wrong question.

The product's promise about playback has two cases, and this module is the
second one only:

*Identified request* — a named song, album or artist. Exact match, then "did you
mean", then a question. Never a guess. Nothing here touches that path.

*Unidentified request* — a mood. There is no "right" track to betray, because
the listener did not have one in mind; choosing is legitimate, but **saying what
was chosen is not optional**. So every reply here reads back what started and
offers «un'altra».

What keeps the two apart is a double filter, and it lives half here and half in
the language packs: the phrase must carry a marker («qualcosa di …», «musica per
…») *and* its tail must resolve to an entry of that pack's ``MOOD_WORDS``. Miss
either one and the request falls through to the existing paths, unchanged. That
is why «metti qualcosa di Vasco Rossi» — which clears the marker — is still a
search for Vasco Rossi and not a mood.

The table below is language-neutral on purpose. The *phrases* people say belong
to a language pack; the mapping from a mood to genres and playlists does not,
because a music library's genre tags don't follow the UI language — an Italian
listener's library says "Classical" as often as "Classica", so both are aliases
of the same mood. This is also the shape T2.5 fills in later: a generated
``mood_seeds.json`` replaces the source of this data without changing the lookup
that reads it, and with the file absent the behaviour is what you see here.

A genre used to play in library order, so the same mood opened on the same
track every evening. The obvious fix was rejected and stays rejected: LMS's
``playlist shuffle 1`` is not "shuffle this queue", it is the player's shuffle
*preference*, and setting it would leave every later «metti The Dark Side of
the Moon» playing out of order with no voice command anywhere to turn it back
off. Trading a repeated opening track for silently shuffling somebody's albums
is not a trade this product gets to make.

``playlistcontrol sort:random`` is the third way, and it is what the loads here
now pass. It is scoped to the single call, touches no preference, and the CLI
documents it as relevant precisely when ``genre_id``, ``artist_id`` or ``year``
is supplied — two of which are the shapes this module loads (``play_local_artist``
serves identified requests, where album order is the right order, and is left
alone). **Its known limit, because it
is a limit and not a fix**: ``sort`` is the *album* sort order, so it
randomises which album opens, not the order of tracks inside it. A mood no
longer starts on the same track every evening, but it is not a true shuffle,
and only a real LMS can say how well it reads in practice — there isn't one
here.

Resolution order is **local library first, then the streaming service**, decided
with Luca on 2026-08-26: a genre out of the listener's own library is music they
demonstrably own, which is the acceptance criterion read literally. Curated
service playlists are the fallback, not the lead.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from actions import ActionResult, Guard, _normalize, is_blocked_item
from lms import LMSError
from messages import msg

# How many library genres to ask LMS for. A library with more distinct genre
# tags than this has bigger problems than the tail of the list being ignored.
GENRE_LIMIT = 200
# Same, for years. Recorded music is not yet 200 years old.
YEAR_LIMIT = 200
# Playlist candidates per service query, as elsewhere in the client.
PLAYLIST_LIMIT = 20

# mood key -> the library axis that means it, best first, and the playlist
# searches to try when the library answers nothing on that axis.
#
# The axis is ``genres`` for almost every entry and ``years`` for a decade —
# an entry carries one or the other, never both, and ``play_mood`` branches on
# which. A decade's ``years`` is the closed interval it covers, because no LMS
# filter anywhere accepts a range: the year the load asks for is a single year
# picked out of that interval.
#
# Genre aliases are matched against the library's own tags two ways: equal when
# normalized ("Classica" == "classica"), or present as a whole word inside a
# longer tag, so "Classic Rock" answers `rock` and "Jazz Vocal" answers `jazz`.
# Whole-word is what keeps "Rockabilly" from answering `rock` — a tag that
# starts alike is not the same tag.
#
# Playlist queries are English because TIDAL and Qobuz name their curated
# playlists in English regardless of the account's country.
# ``Sequence[Any]`` and not ``Sequence[str]``: a decade's ``years`` holds two
# ints, everything else holds strings.
MOODS: Dict[str, Dict[str, Sequence[Any]]] = {
    "relax": {
        "genres": ("Ambient", "New Age", "Chillout", "Chill Out", "Downtempo",
                   "Classical", "Classica", "Easy Listening"),
        "playlists": ("Relaxing", "Calm", "Chill"),
    },
    "sleep": {
        "genres": ("Ambient", "New Age", "Classical", "Classica"),
        "playlists": ("Sleep", "Calm", "Relaxing"),
    },
    "dinner": {
        "genres": ("Jazz", "Bossa Nova", "Lounge", "Soul", "Easy Listening"),
        "playlists": ("Dinner", "Dinner Jazz", "Lounge"),
    },
    "party": {
        "genres": ("Dance", "Disco", "Funk", "House", "Electronic",
                   "Elettronica", "Pop"),
        "playlists": ("Party", "Dance Party", "Feel Good"),
    },
    "happy": {
        "genres": ("Pop", "Funk", "Soul", "Reggae", "Ska", "Disco"),
        "playlists": ("Feel Good", "Happy", "Good Mood"),
    },
    "energetic": {
        "genres": ("Rock", "Electronic", "Elettronica", "Dance", "Punk",
                   "Metal"),
        "playlists": ("Workout", "Energy", "Running"),
    },
    "focus": {
        "genres": ("Ambient", "Minimal", "Classical", "Classica",
                   "Electronic", "Elettronica"),
        "playlists": ("Focus", "Concentration", "Study"),
    },
    "background": {
        "genres": ("Ambient", "Lounge", "Easy Listening", "Jazz", "Classical",
                   "Classica"),
        "playlists": ("Background", "Easy Listening", "Chill"),
    },
    "romantic": {
        "genres": ("Soul", "R&B", "Rhythm and Blues", "Jazz", "Bossa Nova",
                   "Pop"),
        "playlists": ("Romantic", "Love Songs", "Date Night"),
    },
    "melancholy": {
        "genres": ("Blues", "Folk", "Cantautori", "Singer-Songwriter",
                   "Indie", "Alternative"),
        "playlists": ("Melancholy", "Sad Songs", "Rainy Day"),
    },
    "morning": {
        "genres": ("Jazz", "Bossa Nova", "Folk", "Acoustic", "Pop"),
        "playlists": ("Morning", "Wake Up", "Breakfast"),
    },
    # Genre-shaped vague requests ("metti un po' di jazz"). No title, no artist,
    # nothing for the parser to find — the same gap, answered by the same
    # lookup, at no extra cost.
    "classical": {
        "genres": ("Classical", "Classica", "Baroque", "Barocco", "Opera",
                   "Lirica"),
        "playlists": ("Classical", "Classical Essentials"),
    },
    "jazz": {
        "genres": ("Jazz", "Bebop", "Swing", "Bossa Nova"),
        "playlists": ("Jazz", "Jazz Essentials"),
    },
    "rock": {
        "genres": ("Rock", "Classic Rock", "Hard Rock", "Progressive Rock",
                   "Rock Progressivo"),
        "playlists": ("Rock", "Rock Classics"),
    },
    "blues": {
        "genres": ("Blues", "Rhythm and Blues", "R&B"),
        "playlists": ("Blues", "Blues Essentials"),
    },
    # Metadata axes LMS already carries, added in the second pass. Christmas is
    # a genre tag people really do have; "instrumental" and "summer" are not —
    # no library has a tag called either — so both are spelled out as the
    # genres that genuinely ARE that thing.
    "christmas": {
        "genres": ("Christmas", "Natale", "Holiday", "Natalizio"),
        "playlists": ("Christmas", "Christmas Classics"),
    },
    "instrumental": {
        "genres": ("Instrumental", "Strumentale", "Classical", "Classica",
                   "Ambient", "Post-Rock"),
        "playlists": ("Instrumental", "Instrumental Focus"),
    },
    "summer": {
        "genres": ("Reggae", "Latin", "Bossa Nova", "Surf", "Ska"),
        "playlists": ("Summer", "Summer Hits"),
    },
    # Decades: the year axis. See the note above on why the value is an
    # interval and the load is one year out of it.
    "sixties": {
        "years": (1960, 1969),
        "playlists": ("60s", "60s Hits"),
    },
    "seventies": {
        "years": (1970, 1979),
        "playlists": ("70s", "70s Hits"),
    },
    "eighties": {
        "years": (1980, 1989),
        "playlists": ("80s", "80s Hits"),
    },
    "nineties": {
        "years": (1990, 1999),
        "playlists": ("90s", "90s Hits"),
    },
}


def match_mood(tail: Optional[str], table: Dict[str, str]) -> Optional[str]:
    """The mood a spoken tail names, or None.

    ``table`` is a language pack's ``MOOD_WORDS`` (spoken phrase -> mood key).
    The match is on the **whole** normalized tail, never a substring of it:
    a partial match is exactly how a song title would become a mood, and the
    one thing this must not do. Multi-word entries therefore work by being
    the whole tail ("per cena"), not by being found inside one.
    """
    norm = _normalize(tail)
    if not norm:
        return None
    key = table.get(norm)
    if key is None:
        return None
    return key if key in MOODS else None


def _genre_matches(alias: str, tag: Optional[str]) -> bool:
    """True when a library genre tag means this alias — equal, or containing it
    as a whole word ("Classic Rock" for "Rock", but not "Rockabilly")."""
    a, t = _normalize(alias), _normalize(tag)
    if not a or not t:
        return False
    return a == t or re.search(rf"\b{re.escape(a)}\b", t) is not None


def _pick_genre(genres: List[Dict], aliases: Sequence[str],
                exclude) -> Tuple[Optional[Dict], bool]:
    """(chosen, any_matched) — the first library genre matching the mood's
    aliases in order, skipping what «un'altra» already used. ``any_matched``
    tells an empty result apart from an exhausted one, which are two different
    things to say."""
    seen = False
    for alias in aliases:
        for genre in genres:
            if not _genre_matches(alias, genre.get("title")):
                continue
            seen = True
            if _normalize(genre.get("title")) in exclude:
                continue
            return genre, True
    return None, seen


def _pick_year(years: Sequence[int], span: Sequence[int],
               exclude) -> Tuple[Optional[int], bool]:
    """(chosen, any_matched) — ``_pick_genre`` on the other axis: the first
    library year inside the decade, skipping what «un'altra» already used.

    One year, not the whole decade, and that is the deliberate part. Loading
    ten years means one ``cmd:load`` and nine ``cmd:add``, and it leaves
    «un'altra» with nothing left to exclude — so it would either do nothing or
    need a random number generator, and this module has already decided that
    «un'altra» works by exclusion so the tests stay reproducible. One year
    keeps it working exactly as it does for a genre, and keeps the read-back
    honest about what actually started."""
    start, end = span
    seen = False
    for year in years:
        if not start <= year <= end:
            continue
        seen = True
        if str(year) in exclude:
            continue
        return year, True
    return None, seen


def play_mood(lms, key: str, *, stream=None, exclude=(),
              guard: Optional[Guard] = None) -> ActionResult:
    """Start something that fits ``key``, and say what it was.

    ``lms`` plays the local library, ``stream`` (optional) the streaming
    service the request came from. ``exclude`` holds the normalized labels
    «un'altra» has already been given, so a second ask gets a second answer.

    Returns a spoken read-back whose ``terms[0]`` is the chosen label — which
    is what the caller adds to ``exclude`` for the next round.
    """
    mood = MOODS.get(key)
    if mood is None:
        return ActionResult(msg("mood_not_found"), ok=False)
    exclude = {e for e in (_normalize(x) for x in exclude) if e}
    offered = False

    # 1) the listener's own library, on whichever axis this mood carries.
    #
    # The guard filters genre NAMES, which is as far as this can see: loading
    # a genre loads every track in it, so a blocked artist inside an allowed
    # genre still plays. That is exactly the depth of the hole
    # actions.play_local_artist already has (cmd:load artist_id: is the same
    # wholesale load), not a new one — but it is worth naming rather than
    # leaving for someone to find, and closing it means resolving a genre to
    # its tracks and filtering those. A year has no name to filter at all, so
    # a decade is that same hole with nothing to hold on to; the blocklist is
    # about names, and 1985 is not one. Say the rest of it plainly, because it
    # is the part that is worse: a household that blocks "Christmas" does get
    # refused on the genre axis, so the blocklist bites there. On the year axis
    # it cannot bite at all, and one year spans every genre in the library
    # where a genre is one slice of it — this is the only mood axis a kid-safe
    # household cannot restrict. The service-playlist fallback below is still
    # guarded; only the wholesale local load is not.
    if "years" in mood:
        try:
            years = lms.local_years(YEAR_LIMIT)
        except LMSError:
            return ActionResult(msg("err_unreachable"), ok=False)
        year, offered = _pick_year(years, mood["years"], exclude)
        if year is not None:
            try:
                lms.play_local_year(year)
            except LMSError:
                return ActionResult(msg("err_unreachable"), ok=False)
            return ActionResult(msg("playing_mood_year", year=year), ok=True,
                                terms=[str(year)])
    else:
        try:
            genres = lms.local_genres(GENRE_LIMIT)
        except LMSError:
            return ActionResult(msg("err_unreachable"), ok=False)
        if guard and guard.restricted:
            genres = [g for g in genres
                      if not is_blocked_item(g, guard.blocklist)]
        chosen, offered = _pick_genre(genres, mood["genres"], exclude)
        if chosen is not None:
            try:
                lms.play_local_genre(chosen["id"])
            except LMSError:
                return ActionResult(msg("err_unreachable"), ok=False)
            name = chosen.get("title") or ""
            return ActionResult(msg("playing_mood_genre", genre=name), ok=True,
                                terms=[name])

    # 2) the service's curated playlists.
    if stream is not None:
        for query in mood["playlists"]:
            try:
                cands = stream.playlist_candidates(query, PLAYLIST_LIMIT)
            except LMSError:
                return ActionResult(msg("err_unreachable"), ok=False)
            if guard and guard.restricted:
                cands = [c for c in cands
                         if not is_blocked_item(c, guard.blocklist)]
            for cand in cands:
                if not cand.get("id"):
                    continue
                offered = True
                if _normalize(cand.get("title")) in exclude:
                    continue
                try:
                    stream.play_browse_item(cand["id"])
                except LMSError:
                    return ActionResult(msg("err_unreachable"), ok=False)
                name = cand.get("title") or query
                return ActionResult(msg("playing_mood_playlist", name=name),
                                    ok=True, terms=[name])

    # 3) nothing — and the two ways of having nothing are not the same answer.
    # "Out of ideas" ends the thread: something was offered and refused. But
    # having offered NOTHING is not an answer at all, and the caller is told so
    # with ``kind`` so it can give the phrase back to whoever else might handle
    # it: "play some Fun" and "play some Happy" name a band and a song, and a
    # mood that came up empty must not be the reason they stop being searched
    # for.
    if offered:
        return ActionResult(msg("mood_exhausted"), ok=False)
    return ActionResult(msg("mood_not_found"), ok=False, kind="mood_empty")
