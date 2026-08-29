"""What the router remembers between turns, and for how long.

Two open conversations, each with a clock on it: the numbered list just read
out («metti la 2») and the mood just started («un\'altra»). They are the same
kind of thing — something the *previous* turn said that the next one may refer
back to — and both are dangerous without an expiry, so the reason for each
window is written next to it here instead of scattered through the dispatch.

A mixin over :class:`router.Router`, not a collaborator: every method reads the
attributes ``Router.__init__`` sets (``candidates``, ``cand_player``, ``mood``,
``now``). Turning them into an object of their own would have rewritten every
call site — a much larger diff for a split whose whole point is that nothing
behaves differently afterwards.
"""

from __future__ import annotations

import contextlib

import actions
import moods
from messages import msg


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


# An open mood is a conversation ("un'altra") with the same shelf life as an
# open list, and for the same reason: past it, the follow-up phrase belongs to
# whatever the listener is doing now.
MOOD_TTL = 300.0

# An open offer is the third of them, and the shortest-lived thing here in
# practice: a question was asked out loud and the answer comes back in the next
# breath. The window is the list's, for the list's reason — past it, «sì»
# belongs to whatever the listener is doing now, not to a question from five
# minutes ago.
OFFER_TTL = 300.0

# The ``kind`` of a reply that asked a yes/no question. It exists so the turn
# ends here: ``handle_many`` replays a spoken turn once per recognition
# alternative and stops at the first that acted, and an offer has not acted —
# without a kind to stop on, the second-best transcription would be routed
# straight over the question and the offer nobody answered would be gone before
# it was read out. Same shape as ``actions.GATE``, same reason.
OFFER = "offer"


class ConversationState:
    """The open-list and open-mood half of the router."""

    # -- which player this turn acts on ---------------------------------------
    #
    # A room command («metti Time in cucina») aims the turn at another player,
    # and the Router it does that on is shared: http_api.router_for caches one
    # per conversation, and the server runs a thread per connection. Saving
    # self.lms, overwriting it and restoring it in a finally was correct for
    # one turn at a time and wrong for two — A saves the default and aims at
    # Cucina, B saves *Cucina* and aims at Studio, A restores the default, B
    # restores Cucina, and the router is left on Cucina for good. Every later
    # turn on that conversation then acted in a room nobody had asked for.
    # Two automations, or two browser tabs sharing a client id, were enough.

    @property
    def lms(self):
        """The player this turn acts on: where it was aimed, or the default."""
        return getattr(self._aim, "lms", None) or self._base_lms

    @lms.setter
    def lms(self, client):
        self._base_lms = client

    @contextlib.contextmanager
    def _aimed_at(self, player_id):
        """Aim ``self.lms`` at ``player_id`` for this thread, for one turn."""
        previous = getattr(self._aim, "lms", None)
        self._aim.lms = self._base_lms.for_player(player_id)
        try:
            yield
        finally:
            self._aim.lms = previous

    def _expire_candidates(self) -> None:
        """Forget a list nobody picked from in time (see CANDIDATES_TTL)."""
        if self.candidates and self.now() >= self.cand_until:
            self.candidates = None
            self.cand_source = None
            self.cand_player = None
            self.cand_mode = "play"

    def _expire_mood(self) -> None:
        """Forget a mood nobody came back to in time (see MOOD_TTL)."""
        if self.mood is not None and self.now() >= self.mood_until:
            self.mood = None

    def _expire_offer(self) -> None:
        """Forget a question nobody answered in time (see OFFER_TTL)."""
        if self.offer is not None and self.now() >= self.offer_until:
            self.offer = None

    def _offer(self, speech, run):
        """Ask a yes/no question and remember what «sì» would mean.

        ``run`` is a no-argument callable that performs the thing being
        offered, and it is only ever called from the next turn — which is the
        whole point of asking. The one caller today is ``sources.py``, where a
        request has just found out that the service it was aimed at is logged
        out and that another one is connected: substituting silently would put
        music on from a service the user did not name, and saying only "TIDAL
        is not connected" leaves them to say the whole sentence again.
        """
        self.offer = run
        self.offer_until = self.now() + OFFER_TTL
        self._offered = True
        return actions.ActionResult(speech, ok=False, kind=OFFER)

    def _answer_offer(self, yes: bool):
        """Act on the open offer, and close it either way.

        A refusal answers ``ok=True``: nothing is playing, but the turn did
        exactly what was asked of it, and a "no" that reported itself as a miss
        would have ``handle_many`` try the next transcription of the word — and
        a hi-fi that argues with «no» is worse than one that mishears."""
        run, self.offer = self.offer, None
        if not yes:
            return actions.ActionResult(msg("offer_declined"), ok=True)
        return run()

    def _settle_offer(self, result) -> None:
        """Record, for the next turn, whether the question is still open.

        The same asymmetry the mood has, for the same two reasons: a turn that
        ACTED on something else has moved the conversation on, so a later «sì»
        must not answer a question nobody remembers asking; a turn that missed
        has not, and ``handle_many`` replaying a badly transcribed alternative
        must not kill the question before the good alternative arrives."""
        if not self._offered and getattr(result, "ok", False):
            self.offer = None

    def _settle_mood(self, result) -> None:
        """Record, for the next turn, whether the mood is still the topic."""
        self._mood_alive = self._mood_turn or not getattr(result, "ok", False)

    def _play_mood(self, source: str):
        """Start — or re-roll — the open mood, remembering what it picked so
        the next «un'altra» has to answer differently.

        A local source stays local: ``stream=None`` means the curated service
        playlists are not a fallback for someone who asked for their own
        library. Any outcome that isn't a play closes the mood, because both
        of them ("nothing fits", "out of ideas") are the end of that thread —
        re-rolling a mood that just told you it has nothing left is a loop."""
        state = self.mood
        # A re-roll of a room-targeted mood stays in that room (unless this
        # very turn names another one — then self.lms already points there and
        # tagging is the caller's job, exactly like a pick from a list).
        lms, room_suffix = self.lms, ""
        if self.mood_player and not self._room_turn:
            lms = self.lms.for_player(self.mood_player[0])
            room_suffix = msg("in_room", room=self.mood_player[1])
        def stream():
            """Which service, asked only if the library declines.

            Deferred (play_mood resolves it at step 2, not before) because
            ``_stream_name`` now talks to the server to find out which
            services are actually connected, and the library winning over the
            service means the service is never asked at all — including about
            itself. None when nothing is connected, which is the same answer a
            local source gives: the mood is the library's to fill or nobody's,
            and it is the one caller that needs no message of its own for
            that."""
            name = self._stream_name(source)
            return lms.for_service(name) if name else None

        res = moods.play_mood(lms, state["key"],
                              stream=None if source == "local" else stream,
                              exclude=state["used"], guard=self._guard)
        if getattr(res, "ok", False):
            if res.label:
                state["used"].append(res.label)
            self.mood_until = self.now() + MOOD_TTL
        else:
            self.mood = None
        return self._tag(res, room_suffix)

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

    def _needs_choice(self) -> bool:
        """Is this reply waiting for the user to pick from the list it just
        read out?

        The same predicate ``_choices`` decides on, said once and out loud.
        The web app can afford to infer it from a non-empty ``choices``; an
        external client (a Home Assistant blueprint, say) should not have to
        read a meaning — "I asked instead of playing" — out of a list's
        length, so ``/api/v1/command`` states it. It is about THIS turn: an
        open list survives for CANDIDATES_TTL, but only the reply that opened
        it is the one asking."""
        return bool(self._offered or (self._opened and self.candidates))

    def _choices(self) -> list:
        """Tappable choices for the web app, but only for a reply that just
        asked something; ``[]`` otherwise.

        A numbered list reuses ``actions._label``, so the button text matches
        the spoken '1: Title di Artist' read-out. A yes/no offer carries
        ``say`` as well: the client sends that phrase verbatim instead of
        building «metti la N» from the number, because what answers an offer is
        a word, not a position — and the word has to be one this language's
        pack parses, which is why it is the catalog that spells it."""
        if not self._needs_choice():
            return []
        if self._offered:
            return [{"n": 1, "label": msg("offer_yes"), "say": msg("offer_yes")},
                    {"n": 2, "label": msg("offer_no"), "say": msg("offer_no")}]
        return [{"n": i + 1, "label": actions._label(c)}
                for i, c in enumerate(self.candidates)]
