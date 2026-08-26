# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Multi-room targeting (Pro): command any player in the house.

The AGPL core stays policy-free: ``LMSClient.for_player()`` is a generic
mechanism, and the router/server accept an *injected* multiroom object with a
narrow contract (``pro_ok`` / ``players`` / ``extract_room``) — like kid-safe.
This module owns the feature: the license gate, the cached player list, and
the room-phrase understanding («metti Time in cucina», "play X in the
kitchen") with the fuzzy matching that survives ASR spelling («salotto» for a
player named «Salotto Hi-Fi»).

Room extraction is deliberately conservative: a phrase is only treated as a
room when its «in <words>» tail (or head) actually names a player, so
"Breakfast in America" stays a song title.
"""

from __future__ import annotations

import difflib
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple

import actions

# Room matching consults the player list on every command: cache it a few
# seconds so a command costs one LMS round-trip, not two.
CACHE_TTL = 5.0

# Prepositions that may introduce a room. Two Italian ones are left out on
# purpose, and both exclusions are load-bearing — this list is the first and
# cheapest filter, so anything wrongly in it steals phrases before any of the
# weighing below gets a chance to save them:
#   "su" introduces services («su tidal»), not rooms.
#   "da" introduces a *kind* of music, and Italian is full of it: «musica da
#     camera», «romanza da salotto», «valzer da sala». A house with players
#     called Camera, Salotto and Sala is an ordinary house, so admitting "da"
#     would turn chamber music into a command for the bedroom. Nobody asks for
#     a room with it either — it is «in salotto», never «da salotto».
_PREPS = {
    "it": ("in", "nella", "nel", "sulla", "sul"),
    "en": ("in", "on"),
}
_ARTICLES = ("the ", "la ", "il ", "lo ", "l'", "le ", "gli ")


def _fold(text: Optional[str]) -> str:
    """Lowercase + accent-fold («salòtto» == «salotto»)."""
    t = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# How close a spoken room has to be to a player name. The fuzzy path used to
# open at 0.75 with no length floor, and that is not a room-matching rule, it
# is a title-eating one: a player called «Amelia» claimed «metti Breakfast in
# America», and «Paradiso» claimed "Lost in Paradise". A prefix or an exact
# name still wins outright (see below) — this threshold governs only the
# genuinely approximate case, which is ASR spelling, not a different word.
# 0.90 rather than the more obvious 0.85: «paradise» scores 0.875 against a
# player named «Paradiso», and "Lost in Paradise" is a song. One character in
# ten is as far as a room name may drift.
FUZZY_MIN_RATIO = 0.90
# ...and only for something long enough for a ratio to mean anything: on 3
# characters a single shared letter already scores 0.66.
FUZZY_MIN_CHARS = 4

# A library hit weaker than this is not allowed to overrule a player name that
# matched. Without it the comparison below has a hole big enough to drive
# rejected approach #1 through: with an album called «Cucina» in the library,
# «metti musica rilassante in cucina» scores 0.295 as a whole against 0.104 for
# the phrase without the room, so the whole phrase "wins" on a match nobody
# would call a match — and the free tier starts music in the living room
# without saying so. It is the project's existing "a local match has to clearly
# fit the query" constant, used for exactly what it means.
TITLE_MIN_SCORE = actions.LOCAL_CONFIDENT


def _match_player(room: str, players: List[Dict[str, Any]]) -> Optional[Dict]:
    """The player whose name best matches a spoken room, or None. Fuzzy on
    purpose: ASR writes «salotto» for a player named «Salotto Hi-Fi»."""
    room_f = _fold(room)
    for article in _ARTICLES:
        if room_f.startswith(article):
            room_f = room_f[len(article):].strip()
            break
    if not room_f:
        return None
    best, best_score = None, 0.0
    for player in players:
        name_f = _fold(player.get("name"))
        if not name_f or not player.get("playerid"):
            continue
        # A player LMS reports as disconnected is not a room anyone is in:
        # targeting it swallows the command and plays nothing, silently.
        if "connected" in player and not player.get("connected"):
            continue
        score = difflib.SequenceMatcher(None, room_f, name_f).ratio()
        if len(room_f) >= 3 and (name_f.startswith(room_f) or room_f == name_f):
            score = max(score, 0.96)
        elif len(room_f) < FUZZY_MIN_CHARS or score < FUZZY_MIN_RATIO:
            continue   # too short, or too far, for the fuzzy path
        if score > best_score:
            best, best_score = player, score
    return best if best_score >= FUZZY_MIN_RATIO else None


class MultiRoom:
    """The multi-room feature behind the router and the web endpoints.

    ``license_mgr`` may be None (no license infrastructure: everything stays
    gated off). ``get_players`` is the LMS query, injected so the server and
    the tests decide where players come from. ``lms`` is the library client
    :meth:`room_reading_wins` consults; without one it simply never second-
    guesses a room, which is what every caller got before it existed.
    """

    def __init__(self, license_mgr, get_players: Callable[[], list],
                 cache_ttl: float = CACHE_TTL, lms: Optional[Any] = None) -> None:
        self.license = license_mgr
        self.get_players = get_players
        self.cache_ttl = cache_ttl
        self.lms = lms
        self._cache: List[Dict[str, Any]] = []
        self._cached_at = 0.0

    def pro_ok(self) -> bool:
        return self.license is not None and self.license.is_pro()

    def players(self) -> List[Dict[str, Any]]:
        """The player list, cached for a few seconds. Raises like the LMS
        query on failure (the /players endpoint reports it; the voice path
        uses :meth:`_players_safe` instead)."""
        now = time.monotonic()
        if now - self._cached_at > self.cache_ttl:
            self._cache = self.get_players() or []
            self._cached_at = now
        return self._cache

    def _players_safe(self) -> List[Dict[str, Any]]:
        try:
            return self.players()
        except Exception:
            return []

    def room_reading_wins(self, whole: Optional[str],
                          without_room: Optional[str], *, guard=None) -> bool:
        """Is «X in <room>» better read as a room command, or as a title?

        :meth:`extract_room` can only ever produce a *guess*. A player called
        «America» makes «metti breakfast in america» look like a room command,
        and spending that guess as if it were a fact answers a record the
        listener owns with an advertisement. So both readings are put to the
        library and the better one wins: «breakfast in america» names something
        it has and «breakfast» only resembles it (1.000 against 0.848), while
        «bollicine in cucina» is the other way round (0.457 against 1.000).

        Both are scored without ``_score``'s subset floor, over the pool the
        two searches return *together* — two maxima taken over two different
        result sets are not comparable, and the narrower query is the one
        ``count=10`` truncates first.

        ``True`` — keep the room, and today's behaviour with it — on a tie, on
        an empty library, on an unreachable server, and when no library client
        was injected. The asymmetry is the point: refusing costs a turn, while
        acting in the wrong room costs an action somebody has to go and undo.
        """
        if self.lms is None or not whole or whole == without_room:
            return True

        try:
            pool = actions.library_candidates(self.lms, whole, guard=guard)
            if not pool:
                # Nothing answers the whole phrase, so nothing can beat the
                # room and the second search would be waste. This is why an
                # ordinary room command costs three queries and not six.
                return True
            # Deduped as a set, not concatenated as a bag: a row both queries
            # return would otherwise sit in the pool twice. Harmless under
            # max(), and a trap for the next rule that counts or averages.
            pool = actions._dedup_by_title_artist(
                pool + actions.library_candidates(self.lms, without_room, guard=guard))
        except Exception:
            return True
        whole_score = actions.best_match_score(whole, pool, subset_floor=False)
        room_score = actions.best_match_score(without_room, pool, subset_floor=False)
        return not (whole_score >= TITLE_MIN_SCORE and whole_score > room_score)

    def extract_room(self, text: str, lang: str) -> Tuple[str, Optional[Dict]]:
        """``(text_without_room, player)`` when the phrase carries an
        «in <room>» that names a real player; ``(text, None)`` otherwise."""
        players = self._players_safe()
        if not players:
            return text, None
        preps = _PREPS.get(lang) or _PREPS["it"]
        words = text.split()
        # Suffix: «metti X in cucina» (room = the last 1-3 words).
        for n in (3, 2, 1):
            if len(words) >= n + 2 and words[-(n + 1)].lower() in preps:
                player = _match_player(" ".join(words[-n:]), players)
                if player:
                    return " ".join(words[:-(n + 1)]).rstrip(" ,"), player
        # Prefix: «in cucina metti X».
        if len(words) >= 3 and words[0].lower() in preps:
            for n in (3, 2, 1):
                if len(words) >= n + 2:
                    player = _match_player(" ".join(words[1:1 + n]), players)
                    if player:
                        return " ".join(words[1 + n:]), player
        return text, None
