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
from conversation import (CANDIDATES_GRACE, CANDIDATES_TTL, MOOD_TTL,
                          ConversationState)
from intents import IntentTable
from lang import PACKS
from messages import msg, set_lang
from parsing import _source_suffix

# The two windows are defined next to the state they bound, but they are still
# the router's windows: ``router.CANDIDATES_TTL`` has to keep naming the one it
# actually honours.
__all__ = ["Router", "PATTERNS", "MOOD_WORDS",
           "CANDIDATES_TTL", "CANDIDATES_GRACE", "MOOD_TTL"]

# One patterns dict per language pack; ``PATTERNS.get(lang) or PATTERNS["it"]``
# is the it-fallback the whole app relies on. (Kept under this name: the
# tests assert on cross-language key parity through it.)
PATTERNS = {code: pack.PATTERNS for code, pack in PACKS.items()}

# Mood vocabularies, deliberately NOT merged across languages the way the
# number tables below are. A number word is a label for a position and means
# the same thing whichever language says it; a mood word is a content word,
# and merging the vocabularies would widen the set of tails that turn into a
# mood — which is the opposite of this filter's job.
MOOD_WORDS = {code: pack.MOOD_WORDS for code, pack in PACKS.items()}




class Router(ConversationState, IntentTable):
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
        # The open mood (see engine/moods.py): {"key", "used"} while
        # a vague request is live, None otherwise. ``used`` holds the labels
        # already given, so «un'altra» has to find a different answer.
        self.mood = None
        self.mood_until = 0.0
        # (playerid, name) when the mood was started by a room-targeted
        # command, so «un'altra» re-rolls in that room instead of starting
        # music somewhere nobody asked for. Same idea as cand_player.
        self.mood_player = None
        self._mood_turn = False  # this turn acted on the mood
        # Whether the mood is still what the conversation is about, as far as
        # the NEXT turn is concerned. See handle() for the rule.
        self._mood_alive = True
        # The language pack's mood vocabulary for this turn (set in handle()).
        self._mood_words = {}

    #: The play branches of :meth:`_route` that name what they want, in the
    #: order _route tries them (album 5, playlist 6, artist 7, generic 8). The
    #: room gate walks the same list, because a gate that measured «l'album
    #: breakfast in america» while the route searched «breakfast in america»
    #: would find nothing, and answer a record on the disk with an advert.
    _PLAY_BRANCHES = ("album", "playlist", "artist", "generic_play")

    def _play_query(self, t: str, P: dict):
        """The search terms a play would use for ``t``, or ``None`` when ``t``
        asks for no music at all.

        Only the room gate calls this. Step 8 of :meth:`_route` deliberately
        does *not*: by the time the route reaches it, steps 5-7 have already
        declined, so it may consult the generic branch and nothing else. The
        gate has no such ordering — it runs before any of them and has to ask
        about all four.
        """
        for name in self._PLAY_BRANCHES:
            pattern = P.get(name)
            m = pattern.search(t) if pattern else None
            if m:
                return m.group(1).strip()
        if "generic_play_suffix" in P:  # EN: "put Dark Side on"
            m = P["generic_play_suffix"].match(t)
            if m:
                return m.group(1).strip()
        # Last resort, and the gate's alone: a leading play verb with something
        # after it. English «put love on repeat» matches no branch above — the
        # adjacent "put on" is not there and the phrase does not end in "on" —
        # and without this the gate would hand the turn to the room without
        # ever asking whether *Love on Repeat* is on the disk.
        verb = P.get("is_play")
        lead = verb.match(t) if verb else None
        tail = t[lead.end():].strip() if lead else ""
        return tail or None

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
        errors and 'did you mean' questions pass through untouched.

        It goes into the FIRST sentence, which is the same thing as the last
        one for every confirmation that has only one — all of them until the
        mood read-back, which ends by inviting «un'altra» and turned
        «… in cucina» into an instruction about where to say it."""
        if not suffix or not getattr(res, "ok", False) or getattr(res, "kind", None):
            return res
        head, sep, rest = str(res).partition(". ")
        if head.endswith("."):
            head = head[:-1]
        speech = head + suffix + "." + ((" " + rest) if sep else "")
        return actions.ActionResult(speech, ok=True, candidates=res.candidates,
                                    kind=res.kind, terms=res.terms)

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
                    "terms": [], "choices": [], "needs_choice": False,
                    "unmatched": False}
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
                        "choices": self._choices(),
                        "needs_choice": self._needs_choice(),
                        "unmatched": False}
        return {"speech": primary[0], "used": primary[1], "ok": primary[2],
                "terms": list(getattr(primary[0], "terms", [])),
                "choices": self._choices(),
                "needs_choice": self._needs_choice(),
                "unmatched": primary[3]}

    def handle(self, text: str, source: str = "tidal", lang: str = "it") -> str:
        # Reset per turn; _remember/_played set it when this turn opens a list.
        # A bare 'metti la N' pick doesn't re-open one, so its reply carries no
        # buttons (the list was already shown on the previous reply).
        self._opened = False
        self._unmatched = False  # _route sets it on the "non ho capito" path
        self._expire_candidates()
        self._expire_mood()
        # A mood lives only while the conversation is still about it, and the
        # rule is: a turn that ACTED on something else ends it; a turn that
        # was not understood does not. The asymmetry is deliberate, and both
        # halves are load-bearing.
        #
        # Ending it on an action is the safe direction of the two: without it
        # «metti Comfortably Numb» followed by «un'altra» would re-roll a mood
        # from four minutes ago and change the music out from under someone.
        #
        # Surviving a miss is what keeps handle_many honest. It replays the
        # same spoken turn once per recognition alternative, and its contract
        # is that trying a miss has no side effect — an alternative that
        # transcribed badly must not quietly kill the mood before the
        # alternative that transcribed well gets its turn.
        if not self._mood_alive:
            self.mood = None
        self._mood_turn = False
        set_lang(lang)
        P = PATTERNS.get(lang) or PATTERNS["it"]
        self._mood_words = MOOD_WORDS.get(lang) or MOOD_WORDS["it"]
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
        overruled = False
        if self.multiroom is not None:
            stripped, target = self.multiroom.extract_room(t, lang)
            if target is not None:
                # A room name is a GUESS about what the words meant, so before
                # it is spent, both readings go to the library and the better
                # one wins (T2.7b). Only a play can have a title in it: for
                # «pausa in cucina» there is nothing to weigh and nothing is
                # asked, which is what makes rejected approach #2 — pausing the
                # living room — impossible here rather than merely unlikely.
                # One reading for both licenses, deliberately: which record the
                # words name is not a thing a license gets a say in.
                whole = self._play_query(t, P)
                # ``room_q`` may legitimately be None while ``whole`` is not:
                # «play in my room» strips to a bare «play», which names
                # nothing. That is not a reason to skip the library — it is the
                # strongest evidence there is that the "room" was the title,
                # because the room reading leaves nothing to play at all. The
                # library still settles it: with *In My Room* on the disk the
                # song wins, and without it the phrase stays what it also is,
                # «resume, in that room».
                room_q = self._play_query(stripped, P) if whole else None
                if self.multiroom.room_reading_wins(
                        whole, room_q, guard=self._guard):
                    # Answer with the pitch, not a confusing search miss — and
                    # with the room in it, because naming the guess is what
                    # makes a wrong one visible where the library had no
                    # opinion either way.
                    if not self.multiroom.pro_ok():
                        return msg("room_needs_pro",
                                   room=target.get("name") or "")
                    t = stripped
                else:
                    # The words name a record we own. Play it, here, on the
                    # full phrase — «metti breakfast in america» is Supertramp,
                    # not a command for a player that happens to be called
                    # America.
                    target = None
                    # ...and say so, to whoever could have had the room. This
                    # turn has been judged not to be about a room, so a list
                    # left open in one must not capture it either.
                    overruled = self.multiroom.pro_ok()
                    self.cand_player = None
        self._room_turn = target is not None
        if target is None:
            result = self._route(t, source, P)
            if self._opened:
                self.cand_player = None  # a fresh list belongs to this player
            if self._mood_turn:
                self.mood_player = None  # a mood started here stays here
            self._settle_mood(result)
            if overruled:  # _tag itself skips misses and questions
                result = self._tag(result, msg("read_as_title"))
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
        if self._mood_turn:
            self.mood_player = (target["playerid"], room)
        self._settle_mood(result)
        return self._tag(result, msg("in_room", room=room))
