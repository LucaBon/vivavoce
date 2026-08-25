"""Local intent router (language-agnostic dispatch).

Maps free text (from the browser's speech recognition, or a text box) to the
action functions of the shared engine (``actions.py`` + ``lms.py``).
No cloud — just rules over the transcribed text.

Language: the patterns live in per-language packs under ``localvoice/lang/``
(``it.py``, ``en.py`` — contract in ``lang/base.py``); the client sends the
language it is speaking (the page's mic-language selector) and the reply
comes back in that language via the ``messages`` catalog. Unsupported
languages fall back to Italian. This module owns only the dispatch flow and
the state; it declares no language knowledge of its own.

Music sources:
- **local library** (USB disk) and the **streaming services** (TIDAL, Qobuz).
  Ambiguous commands ("riproduci X" / "play X") follow the ``source`` passed by
  the UI selector; "auto" tries local first, then the configured default
  streaming service. Explicit phrases always win: "dalla mia musica …" /
  "from my music …" forces local, "da tidal …" / "on tidal …" force a service.

State (the last read-out list) is kept in-instance for the "metti la N" /
"play number N" choice.
"""

from __future__ import annotations

import re
import time

import actions
from lang import PACKS
from messages import msg, set_lang

# One patterns dict per language pack; ``PATTERNS.get(lang) or PATTERNS["it"]``
# is the it-fallback the whole app relies on. (Kept under this name: the
# tests assert on cross-language key parity through it.)
PATTERNS = {code: pack.PATTERNS for code, pack in PACKS.items()}

# The word tables are merged across every registered language on purpose:
# the recogniser's language and the phrasing don't always agree ("metti la
# three"), and a merged lookup answers both for free.
_NUM_WORDS = {}
_ORDINAL_WORDS = {}
_MINUTE_WORDS = {}
for _pack in PACKS.values():
    _NUM_WORDS.update(_pack.NUM_WORDS)
    _ORDINAL_WORDS.update(_pack.ORDINAL_WORDS)
    _MINUTE_WORDS.update(_pack.MINUTE_WORDS)


def _as_number(token, ordinals=False):
    """A spoken position -> int, or None if the token isn't a number."""
    token = (token or "").strip().lower()
    if token.isdigit():
        return int(token)
    number = _NUM_WORDS.get(token)
    if number is None and ordinals:
        number = _ORDINAL_WORDS.get(token)
    return number


def _parse_minutes(tail):
    """A spoken duration ('30 minuti', "mezz'ora", 'an hour') -> minutes, or
    None when the tail isn't a duration (then the phrase wasn't a sleep
    command and routing falls through). Tries every language's DURATIONS:
    the patterns are language-disjoint, so the order across packs is moot."""
    t = (tail or "").strip().lower()
    for pack in PACKS.values():
        for pattern, spec in pack.DURATIONS:
            m = pattern.match(t)
            if not m:
                continue
            if spec == "hours":
                token = m.group(1)
                hours = (int(token) if token.isdigit()
                         else _MINUTE_WORDS.get(token))
                return hours * 60 if hours else None
            if spec == "minutes":
                token = m.group(1)
                return int(token) if token.isdigit() else _MINUTE_WORDS.get(token)
            return spec
    return None


# Web Speech rarely transcribes the service names right — they aren't real
# words, so each recognizer writes what it hears in its own language:
#   qobuz -> it «kobuz»/«cobus», en "kaboots"/"cabooze", es «cobús»/«cobos»/
#            «que bus», de «Kobutz»/«Kobuts»/«Kobus», fr «cobusse»/«kobuze»
#   tidal -> it «taidal»/«tidol», en "title", es «Vidal»/«tídal»,
#            de «Titel»/«Taidel»/«Tiedal», fr «tidale»/«tidalle»
# The explicit-source phrase must match what was *heard*, so each service name
# expands to a sound-alike pattern instead of the literal spelling.
_SERVICE_SOUNDS = {
    "tidal": r"(?:t(?:ai|ay|ei|ie|i|í|y)[\s\-]?d[aeoà]?l{1,2}e?"
             r"|titles?|titel|tider|tida|vidal)",
    "qobuz": r"(?:[qkc](?:u?[oóa]|ue)[\s\-]?b(?:oo|[uoaúù])[\s\-]?"
             r"(?:ts|tz|zz|ss|z|s)e?)",
}


def _service_re(name: str) -> str:
    """Regex snippet matching a service name as ASR may transcribe it."""
    return _SERVICE_SOUNDS.get(name, re.escape(name))


# Display names for the source tag in play confirmations.
_SERVICE_LABELS = {"tidal": "TIDAL", "qobuz": "Qobuz"}


def _source_suffix(name) -> str:
    """The localized ' da TIDAL' / ' from your music' tag for a source name
    ('local' or a service), so play replies say which source answered."""
    if not name:
        return ""
    if name == "local":
        return msg("from_local")
    return msg("from_service", service=_SERVICE_LABELS.get(name, name))


# How long a read-out list stays pickable. Without a clock on it, the list
# lived for the life of the process: days later a one-word title («Uno»,
# «Sei», «Prima») was read as a pick from a list nobody remembered opening,
# instead of being searched — and because it "matched", the web app never
# offered its "report this phrase" button either.
CANDIDATES_TTL = 300.0
# After a pick has been acted on the list is nearly done: long enough that the
# choice buttons still on screen keep working ("no, the other one"), short
# enough that it can't hijack anything later.
CANDIDATES_GRACE = 30.0


class Router:
    def __init__(self, lms, default_service="tidal", services=("tidal", "qobuz"),
                 kidsafe=None, client_id="default", multiroom=None,
                 now=time.monotonic):
        self.lms = lms
        # Multi-room (Pro): an injected feature object (pro/multiroom.py) with
        # a narrow contract — extract_room(text, lang) and pro_ok(). Like
        # kid-safe, None (the default) disables the feature entirely; the
        # AGPL router only calls the contract, it owns no room logic.
        self.multiroom = multiroom
        # Streaming sources this router accepts as a ``source`` value; anything
        # else streams from ``default_service`` (also the "auto" fallback).
        self.default_service = default_service
        self.services = tuple(services)
        # Kid-safe (Pro): one Router per browser/client, so the guard state is
        # per-client too. None (the default) keeps everything transparent.
        self.kidsafe = kidsafe
        self.client_id = client_id
        self._guard = None  # computed per handle() call
        self.now = now
        self.candidates = None  # candidates from the last list command
        # When the open list stops being pickable (see CANDIDATES_TTL).
        self.cand_until = 0.0
        # Where those candidates play from ('local' or a service name), so a
        # follow-up pick's confirmation can say the source too.
        self.cand_source = None
        # How a pick from the last opened list is acted on: 'play' (replace
        # the queue and start it — every list before the queue feature),
        # 'add' or 'insert' (see actions.play_song). Set only when a NEW list
        # opens (_remember/_played), so it persists across turns exactly like
        # cand_source.
        self.cand_mode = "play"
        # (playerid, name) when the list was opened by a room-targeted command,
        # so «metti la 2» keeps playing in that room; None = default player.
        self.cand_player = None
        self._room_turn = False  # this turn already carries a room override
        # True when THIS turn opened a numbered list (a list command or a
        # 'did you mean'), so the web client can render tappable choice buttons
        # only for the reply that offers them, not on every later reply.
        self._opened = False
        # True when the last handle() fell through every pattern ("non ho
        # capito"): the web client offers the privacy-first "report this
        # phrase" button only then — an understood-but-failed command (LMS
        # down, no search results) is not a parser gap.
        self._unmatched = False

    def _stream_name(self, source):
        """The streaming service a request goes to: ``source`` when it names a
        known service, else the default streaming service."""
        return source if source in self.services else self.default_service

    def _stream(self, source):
        """The LMS client for a streaming request (see :meth:`_stream_name`)."""
        return self.lms.for_service(self._stream_name(source))

    def _tag(self, res, suffix: str):
        """Splice the source tag into a play confirmation ('Riproduco Time.' ->
        'Riproduco Time da Qobuz.'). Only acted-on plays are tagged: misses,
        errors and 'did you mean' questions pass through untouched."""
        if not suffix or not getattr(res, "ok", False) or getattr(res, "kind", None):
            return res
        speech = (res[:-1] if res.endswith(".") else str(res)) + suffix + "."
        return actions.ActionResult(speech, ok=True, candidates=res.candidates,
                                    kind=res.kind, terms=res.terms)

    def _expire_candidates(self) -> None:
        """Forget a list nobody picked from in time (see CANDIDATES_TTL)."""
        if self.candidates and self.now() >= self.cand_until:
            self.candidates = None
            self.cand_source = None
            self.cand_player = None
            self.cand_mode = "play"

    def _used_list(self) -> None:
        """A pick was acted on: the list has done its job. Kept alive for a
        short grace window so the choice buttons still on screen keep working,
        then gone."""
        self.cand_until = min(self.cand_until, self.now() + CANDIDATES_GRACE)

    def _open_list(self, src, mode="play") -> None:
        self.cand_source = src
        self.cand_mode = mode
        self.cand_until = self.now() + CANDIDATES_TTL
        self._opened = True

    def _remember(self, result: dict, src=None) -> str:
        self.candidates = result["candidates"] or None
        self._opened = bool(self.candidates)
        if self.candidates:
            # these lists are always meant to be played
            self._open_list(src, "play")
        return result["speech"]

    def _played(self, result, src=None, mode="play"):
        """Remember any 'did you mean' candidates a play result carried (and
        their source/mode), so a follow-up 'metti la N' / name-pick can act
        on them the same way (play/add/insert)."""
        cands = getattr(result, "candidates", None)
        if cands:
            self.candidates = cands
            self._open_list(src, mode)
        return result

    def _resolve(self, arg: str, stream_fn, source: str):
        guard = self._guard
        if source == "local":
            return self._played(
                actions.play_local(self.lms, arg, guard=guard), "local")
        name = self._stream_name(source)
        stream = self.lms.for_service(name)
        if source == "auto":
            # Auto: prefer a confident local-library hit, else fall back to the
            # default streaming service (no cascading across services).
            # play_local only plays when it matches, so a miss has no effect.
            res = actions.play_local(self.lms, arg, guard=guard)
            if getattr(res, "ok", False):
                return self._played(res, "local")
        return self._played(
            self._tag(stream_fn(stream, arg, guard=guard), _source_suffix(name)),
            name)

    def _resolve_queue(self, arg: str, mode: str, source: str):
        """Like :meth:`_resolve`, but for a song queued (mode: 'add' or
        'insert') instead of played — only play_song/play_local accept a
        queue mode. No explicit source-override phrases ("da tidal ...",
        "dalla mia musica ...") for queue commands: out of scope, the UI
        source selector still decides where a queued song comes from."""
        guard = self._guard
        if source == "local":
            return self._played(
                actions.play_local(self.lms, arg, mode=mode, guard=guard),
                "local", mode=mode)
        name = self._stream_name(source)
        stream = self.lms.for_service(name)
        if source == "auto":
            res = actions.play_local(self.lms, arg, mode=mode, guard=guard)
            if getattr(res, "ok", False):
                return self._played(res, "local", mode=mode)
        return self._played(
            self._tag(actions.play_song(stream, arg, mode=mode, guard=guard),
                      _source_suffix(name)),
            name, mode=mode)

    def handle_many(self, alternatives, source: str = "tidal", lang: str = "it") -> dict:
        """Try each speech-recognition alternative until one is a hit.

        Web Speech (it-IT) often mangles English names ('Audioslave' -> 'sfigati');
        a lower-ranked alternative frequently transcribes them better. Playback
        happens only on a hit, so trying a miss has no side effect. Returns
        ``{'speech', 'used'}`` where ``used`` is the alternative that was kept
        (the primary one if none matched)."""
        set_lang(lang)
        alts = [a for a in (alternatives or []) if (a or "").strip()]
        if not alts:
            return {"speech": msg("heard_nothing"), "used": "", "ok": False,
                    "terms": [], "choices": [], "unmatched": False}
        primary = None
        for alt in alts:
            speech = self.handle(alt, source, lang)
            # A result is a hit when it acted on the request. ActionResult carries
            # an explicit ``.ok``; for any plain string we fall back to the old
            # "Non ..." heuristic so nothing regresses (Italian-only, harmless
            # in English: EN misses are ActionResults and carry .ok).
            ok = getattr(speech, "ok", not speech.strip().lower().startswith("non "))
            if primary is None:
                primary = (speech, alt, ok, self._unmatched)
            if ok:
                return {"speech": speech, "used": alt, "ok": True,
                        "terms": list(getattr(speech, "terms", [])),
                        "choices": self._choices(), "unmatched": False}
        return {"speech": primary[0], "used": primary[1], "ok": primary[2],
                "terms": list(getattr(primary[0], "terms", [])),
                "choices": self._choices(), "unmatched": primary[3]}

    def _choices(self) -> list:
        """Tappable numbered choices for the web app, but only for a reply that
        just opened a list; ``[]`` otherwise. Reuses ``actions._label`` so the
        button text matches the spoken '1: Title di Artist' read-out."""
        if not self._opened or not self.candidates:
            return []
        return [{"n": i + 1, "label": actions._label(c)}
                for i, c in enumerate(self.candidates)]

    def handle(self, text: str, source: str = "tidal", lang: str = "it") -> str:
        # Reset per turn; _remember/_played set it when this turn opens a list.
        # A bare 'metti la N' pick doesn't re-open one, so its reply carries no
        # buttons (the list was already shown on the previous reply).
        self._opened = False
        self._unmatched = False  # _route sets it on the "non ho capito" path
        self._expire_candidates()
        set_lang(lang)
        P = PATTERNS.get(lang) or PATTERNS["it"]
        t = (text or "").strip()
        # Dictation often appends final punctuation ("Metti la 2."): it would
        # break the $-anchored patterns (picks, suffix forms) and leak into the
        # search terms, so strip it.
        t = re.sub(r"[.!?…]+$", "", t).strip()
        if not t:
            return msg("heard_nothing")

        # Kid-safe guard for this request: restrictive only when the feature is
        # enabled and this client isn't PIN-unlocked. Recomputed per turn so an
        # unlock/lock takes effect immediately.
        self._guard = (self.kidsafe.guard_for(self.client_id)
                       if self.kidsafe else None)

        # Room targeting (Pro, pro/multiroom.py): a one-shot retarget of this
        # turn to the named player (the UI selector rules every other turn).
        target = None
        if self.multiroom is not None:
            stripped, target = self.multiroom.extract_room(t, lang)
            if target is not None:
                # Answer with the pitch, not a confusing search miss.
                if not self.multiroom.pro_ok():
                    return msg("pro_required")
                t = stripped
        self._room_turn = target is not None
        if target is None:
            result = self._route(t, source, P)
            if self._opened:
                self.cand_player = None  # a fresh list belongs to this player
            return result
        saved = self.lms
        self.lms = saved.for_player(target["playerid"])
        try:
            result = self._route(t, source, P)
        finally:
            self.lms = saved
        room = target.get("name") or ""
        if self._opened:
            # «metti la 2» after a room-opened list keeps playing in that room.
            self.cand_player = (target["playerid"], room)
        return self._tag(result, msg("in_room", room=room))

    def _route(self, t: str, source: str, P: dict) -> str:
        # 0) kid-safe voice management (Pro; list/edit gated on the PIN unlock).
        if self.kidsafe:
            m = (P["block_add"].match(t) or P["block_remove"].match(t)
                 or P["block_list"].match(t))
            if m:
                if not self.kidsafe.pro_ok():
                    return msg("pro_required")
                is_owner = self.kidsafe.is_unlocked(self.client_id)
                if P["block_add"].match(t):
                    return actions.add_block(
                        self.kidsafe.store,
                        P["block_add"].match(t).group(1).strip(),
                        is_owner=is_owner)
                if P["block_remove"].match(t):
                    return actions.remove_block(
                        self.kidsafe.store,
                        P["block_remove"].match(t).group(1).strip(),
                        is_owner=is_owner)
                return actions.list_blocks(self.kidsafe.store, is_owner=is_owner)

        # 0b) queue management (song-level: "aggiungi X alla coda" / "add X to
        # the queue", "metti X dopo questa" / "play X next", clear/list) and
        # favorites/radio. Checked here, ahead of `is_play` and the transport
        # block below, on purpose: "aggiungi"/"add ... to the queue" aren't
        # play verbs, so `is_play` would stay False for them and let a title
        # containing a bare transport word ("aggiungi Stop alla coda") get
        # mistaken for actions.pause() before ever reaching these patterns —
        # each one here is anchored on its own distinctive marker phrase
        # ("alla coda"/"to the queue", "dopo questa"/"next", ...), so moving
        # them first can't itself swallow a genuine transport command. The UI
        # source selector decides where a queued song comes from, exactly
        # like a plain play request (step 8) — explicit "da tidal .../from my
        # music ..." overrides aren't supported for queue commands (out of
        # scope; those phrases still work for a plain play request).
        if P["queue_clear"].search(t):
            return actions.clear_queue(self.lms)
        if P["queue_list"].search(t):
            return actions.queue_list(self.lms, guard=self._guard)
        m = P["queue_add"].search(t)
        if m:
            return self._resolve_queue(m.group(1).strip(), "add", source)
        m = P["queue_insert"].search(t)
        if m:
            return self._resolve_queue(m.group(1).strip(), "insert", source)
        # Favorites & radio — LMS core feature, source-independent (not a
        # streaming service, so the source selector doesn't apply).
        if P["favorites"].search(t):
            return actions.play_favorites(self.lms, guard=self._guard)
        m = P["radio"].search(t)
        if m:
            return actions.play_radio(self.lms, m.group(1).strip(), guard=self._guard)

        # A play command carries a title after the verb; its transport-sounding
        # words ("Don't Stop Me Now" -> "stop") must NOT be mistaken for
        # transport controls, or the song is never played. "in pausa"/"on pause"
        # stays an explicit pause even with a play verb ("metti in pausa").
        is_play = bool(P["is_play"].search(t))

        # 1) transport & info (source-independent). The sleep timer goes first:
        # «spegni/stop tra 30 minuti» contains transport words, but only counts
        # when its tail really parses as a duration — which is also why it is
        # NOT gated on is_play: «metti in pausa tra 30 minuti» carries a play
        # verb, and used to reach pause_explicit and pause the music at once.
        # The duration requirement is the guard a title needs.
        if not is_play and P["sleep_cancel"].search(t):
            return actions.cancel_sleep(self.lms)
        m = P["sleep"].search(t)
        if m:
            minutes = _parse_minutes(m.group(1))
            if minutes:
                return actions.set_sleep(self.lms, minutes)
        if P["pause_explicit"].search(t) or (not is_play and P["pause"].search(t)):
            return actions.pause(self.lms)
        # Bare "play" is a resume even though "play" is also a play verb.
        if P["resume_explicit"].match(t) or (not is_play and P["resume"].search(t)):
            return actions.resume(self.lms)
        if not is_play and P["next"].search(t):
            return actions.next_track(self.lms)
        if not is_play and P["prev"].search(t):
            return actions.previous_track(self.lms)
        # The loose forms («più forte», "louder") name no control, so a title
        # can be one: they only count when nothing asked to play something.
        if P["vol_up"].search(t) or (not is_play and P["vol_up_loose"].search(t)):
            return actions.change_volume(self.lms, "up")
        if P["vol_down"].search(t) or (not is_play and P["vol_down_loose"].search(t)):
            return actions.change_volume(self.lms, "down")
        # Gated by is_play so a title like "What Is This Feeling" still plays.
        if not is_play and P["nowplaying"].search(t):
            return actions.now_playing(self.lms)

        # 2) choose from the last read-out list by position. Accepts a digit or a
        # spoken number word ("la 2" / "the two", "numero tre" / "number three");
        # ASR gives words, not digits. The explicit forms answer even with no
        # open list (helpful hint); a bare numeral only counts as a pick while a
        # list is open, so it can't swallow an unrelated one-word command.
        m = P["choose_number"].match(t) or P["choose_article"].match(t)
        number = _as_number(m.group(1), ordinals=bool(self.candidates)) if m else None
        if number is None and self.candidates:
            bare = re.match(r"([a-z0-9]+)\s*$", t, re.I)
            number = _as_number(bare.group(1), ordinals=True) if bare else None
        if number is not None:
            # A pick from a room-opened list keeps playing in that room (unless
            # this very turn names another one — then self.lms already points
            # there and tagging is the caller's job).
            pick_lms, room_suffix = self.lms, ""
            if self.cand_player and not self._room_turn:
                pick_lms = self.lms.for_player(self.cand_player[0])
                room_suffix = msg("in_room", room=self.cand_player[1])
            picked = actions.choose_from(pick_lms, self.candidates, number,
                                         mode=self.cand_mode, guard=self._guard)
            if getattr(picked, "ok", False):
                self._used_list()
            return self._tag(
                self._tag(picked, _source_suffix(self.cand_source)),
                room_suffix)

        # 3) explicit source override phrases (win over the selector). Service
        # phrases route only the generic play_song; album/artist follow the
        # selector.
        m = P["local_prefix"].search(t)
        if m:
            return self._played(actions.play_local(self.lms, m.group(1).strip(),
                                                   guard=self._guard), "local")
        m = P["local_suffix"].search(t)
        if m:
            return self._played(actions.play_local(self.lms, m.group(1).strip(),
                                                   guard=self._guard), "local")
        for service in self.services:
            m = re.search(P["service"].format(s=_service_re(service)), t, re.I)
            if m:
                res = actions.play_song(self.lms.for_service(service),
                                        m.group(1).strip(), guard=self._guard)
                return self._played(self._tag(res, _source_suffix(service)), service)

        # 4) lists that open a numbered choice
        m = P["albums_list"].search(t)
        if m:  # "quali album ho di X" / "which albums do I have by X" -> local
            return self._remember(
                actions.local_albums_list(self.lms, m.group(1).strip(),
                                          guard=self._guard), "local")
        m = P["toptracks"].search(t)
        if m:  # top tracks -> streaming (selected or default service)
            return self._remember(
                actions.top_tracks_list(self._stream(source), m.group(1).strip(),
                                        guard=self._guard),
                self._stream_name(source))

        # 4b) name-based choice from the last read-out list (only while a list is
        # open). "metti Supernatural" / "play Supernatural" / bare "Supernatural"
        # -> the remembered candidate, never a fresh whole-library search.
        # choose_by_name returns None when nothing matches ("not a selection"),
        # so routing continues to the generic branches below.
        if self.candidates:
            m = P["name_pick"].match(t)
            if m:
                pick_lms, room_suffix = self.lms, ""
                if self.cand_player and not self._room_turn:
                    pick_lms = self.lms.for_player(self.cand_player[0])
                    room_suffix = msg("in_room", room=self.cand_player[1])
                chosen = actions.choose_by_name(
                    pick_lms, self.candidates, m.group(1).strip(),
                    mode=self.cand_mode, guard=self._guard
                )
                if chosen is not None:
                    if getattr(chosen, "ok", False):
                        self._used_list()
                    return self._tag(
                        self._tag(chosen, _source_suffix(self.cand_source)),
                        room_suffix)

        # 5) album — streaming or local per selector
        m = P["album"].search(t)
        if m:
            return self._resolve(m.group(1).strip(), actions.play_album, source)

        # 6) playlist (streaming: selected or default service)
        m = P["playlist"].search(t)
        if m:
            name = self._stream_name(source)
            return self._tag(
                actions.play_playlist(self.lms.for_service(name),
                                      m.group(1).strip(), guard=self._guard),
                _source_suffix(name))

        # 7) artist — streaming or local per selector
        m = P["artist"].search(t)
        if m:
            return self._resolve(m.group(1).strip(), actions.play_artist, source)

        # 8) generic play — streaming or local per selector
        m = P["generic_play"].search(t)
        if not m and "generic_play_suffix" in P:  # EN: "put Dark Side on"
            m = P["generic_play_suffix"].match(t)
        if m:
            return self._resolve(m.group(1).strip(), actions.play_song, source)

        self._unmatched = True
        return msg("router_fallback")
