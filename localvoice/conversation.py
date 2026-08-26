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


class ConversationState:
    """The open-list and open-mood half of the router."""

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
        stream = (None if source == "local"
                  else lms.for_service(self._stream_name(source)))
        res = moods.play_mood(lms, state["key"], stream=stream,
                              exclude=state["used"], guard=self._guard)
        if getattr(res, "ok", False):
            if res.terms:
                state["used"].append(res.terms[0])
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
        return bool(self._opened and self.candidates)

    def _choices(self) -> list:
        """Tappable numbered choices for the web app, but only for a reply that
        just opened a list; ``[]`` otherwise. Reuses ``actions._label`` so the
        button text matches the spoken '1: Title di Artist' read-out."""
        if not self._needs_choice():
            return []
        return [{"n": i + 1, "label": actions._label(c)}
                for i, c in enumerate(self.candidates)]
