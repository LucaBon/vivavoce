"""Which streaming services this household can actually play from.

Written once and mixed into every backend, for the reason ``resilience.py``
gives about its own three: this is not a fact about LMS, it is a fact about
streaming plugins, and no backend should have to discover it the hard way.

**Why asking is not enough.** A plugin that is logged OUT is visibly out — its
menu is one "authenticate in Settings" notice, it has no search node, and
``can_search`` catches it before anything is played. A plugin whose
subscription has ENDED, or whose token has expired, looks perfect from that
distance: it browses, it searches, it hands back the right track with a
playable-looking url, and it refuses only the audio. Nothing that can be asked
before playing tells the two apart. So this module does not ask; it watches
what happens after a play, and remembers.

**Two shapes of silence, and they are caught at different moments.**
``engine/playback.py`` catches the two that show up straight away: a single
track that leaves the player at stop, and a queue that walks through itself
failing every entry. The third one has to wait — a player that says «play» and
never advances a second looks exactly like a healthy stream filling its buffer
for the first three seconds, so :meth:`SilentServices.settle_pending` settles
it on the NEXT request instead of making this one wait for it.

**What is remembered, and for how long.** A verdict that dies with the process
would have every household buy the same silent play again after every restart,
so the mark is handed a store (:meth:`remember_silence_in`) and the app keeps
it next to the licence. It is not configuration and nobody edits it: it is
what the app learned. It expires on its own after :data:`PLAYBACK_MISS_TTL`,
it is cleared the moment the service is named out loud — asking for TIDAL by
name is not a request to be routed around — and it is cleared by proof of
life, so a mark earned during a network hiccup lifts itself the next time that
service plays a note.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .errors import PlayerError

#: How long a service is taken at its word after playing nothing, in seconds.
#:
#: A day, because the fact it records is usually a fact about the household —
#: a subscription that ended — and re-testing that every few minutes costs a
#: real play into a silent room each time. The two ways out are both faster
#: than the clock and both come from the house rather than from a timer:
#: naming the service clears the mark, and so does one second of audio from
#: it. What the day really bounds is the case nobody says out loud: a service
#: that went down on its own and came back.
PLAYBACK_MISS_TTL = 24 * 3600.0

#: How long after a start the queue must have moved for that start to count as
#: audio, in seconds. Past the three a healthy stream was measured spending on
#: its buffer with the elapsed time at zero, so that a stream still filling up
#: is never mistaken for one that will never play.
PLAYBACK_PROOF_AFTER = 5.0


class SilentServices:
    """What a client remembers about services that played nothing.

    The state is created in the client's ``__init__`` (``_init_silence``) and
    mutated in place, never rebound, so the shallow copies that ``for_service``
    and ``for_player`` hand out SHARE it — "TIDAL plays nothing today" is a
    fact about the server, not about which clone asked. Same reasoning as the
    search-node cache and the breaker next door.
    """

    #: Overridable per backend, though no backend has had a reason to.
    PLAYBACK_MISS_TTL = PLAYBACK_MISS_TTL
    PLAYBACK_PROOF_AFTER = PLAYBACK_PROOF_AFTER

    #: Wall clock, not ``monotonic``: these marks outlive the process.
    now = staticmethod(time.time)

    def _init_silence(self) -> None:
        self._silent_until: Dict[str, float] = {}
        self._pending: Dict[str, Any] = {}
        self._silence_store: Optional[Any] = None

    # -- where the marks live ---------------------------------------------
    def remember_silence_in(self, store) -> None:
        """Give the marks somewhere to survive a restart.

        ``store`` is anything with ``read() -> dict`` and ``write(dict)``; the
        app hands in a file next to the licence (``localvoice/servicestate.py``)
        and the engine never learns where that is. Called once, on the client
        the app builds, before any clone exists.
        """
        self._silence_store = store
        remembered = store.read() or {}
        self._silent_until.clear()
        self._silent_until.update(
            {k: float(v) for k, v in remembered.items()
             if isinstance(v, (int, float))})

    def _save(self) -> None:
        if self._silence_store is not None:
            self._silence_store.write(dict(self._silent_until))

    def _service_key(self) -> str:
        """Which service a mark is about. The registry name, not the CLI tag:
        Spotify answers to ``spotty`` on an LMS and to ``spotify`` everywhere
        else, and the fact being remembered is about Spotify."""
        return getattr(self.service, "name", "") or ""

    # -- learning ----------------------------------------------------------
    def note_playback_failure(self) -> None:
        """Remember that this service accepted something and played none of it.
        Unaimed there is no service to blame, and nothing is remembered."""
        self._mark(self._service_key())

    def forget_playback_failure(self) -> None:
        """Take the mark off: this service is being asked for on purpose."""
        self._unmark(self._service_key())

    def note_playback_started(self) -> None:
        """Record that a start survived its first look, so the next request can
        settle whether any audio ever came of it (:meth:`settle_pending`)."""
        key = self._service_key()
        if key:
            self._pending.clear()
            # The player too: multi-room means the next request can arrive
            # from another room, and an idle player in the living room is no
            # evidence about what the kitchen was asked to play.
            self._pending.update({"service": key, "at": self.now(),
                                  "player": self.player_id})

    def settle_pending(self) -> None:
        """Close the book on the last start, if enough time has passed.

        The third shape of silence: the player took the track, said «play» and
        never moved. Only time tells that from a stream filling its buffer, so
        it is read here — at the top of a later request, where the wait has
        already happened by itself — rather than by holding up the reply that
        started it.

        Nothing is concluded from a player that cannot be reached. Moving at
        all — a second played, or a queue past its first entry — is proof of
        life, and lifts an old mark too: a service that failed during a
        network hiccup should not stay out for a day once it is demonstrably
        playing. A moved queue position is NOT proof of anything — it is half
        of what a walking queue looks like (``playback._walked_away``) — so
        the only thing that lifts a mark here is a second actually played.

        Three readings, three answers, and the third one is a refusal: a
        player at rest that has played nothing says nothing, because it is
        also what a track that finished and one somebody stopped look like. A
        version of this that read that as failure marked a perfectly good
        service for a day every time a song ended.

        What it cannot tell apart, said plainly: somebody who started
        something else from another app in those five seconds, and whose track
        happens to be buffering at zero when we look, is read as our own start
        having failed. The mark that earns is lifted by the next second of
        audio from that service, which is the same self-correction the hiccup
        case relies on.
        """
        pending = self._pending
        if not pending or self.now() - pending["at"] < self.PLAYBACK_PROOF_AFTER:
            return
        if pending.get("player") != self.player_id:
            return
        key = pending["service"]
        self._pending.clear()
        try:
            now = self.now_playing_info()
        except PlayerError:
            return
        if not now:
            return
        if (now.get("elapsed") or 0) > 0:
            self._unmark(key)                       # it played. Nothing else is.
        elif now.get("mode") == "play" or (now.get("index") or 0) > 0:
            self._mark(key)
        # Anything else is a player at rest with nothing played, and that is
        # not evidence: it is exactly what a track that finished, or one
        # somebody stopped, leaves behind.

    # -- using -------------------------------------------------------------
    def can_play(self) -> bool:
        """Whether this service can be expected to deliver AUDIO right now.

        ``can_search`` asks the catalogue half of the plugin, and is the right
        question for "was anybody actually asked?"; this is the right question
        for "who should we ask?". They differ exactly when a subscription has
        ended — the case that used to be discovered one silent room at a time.
        """
        key = self._service_key()
        until = self._silent_until.get(key)
        if until is not None:
            if until > self.now():
                return False
            self._unmark(key)
        return self.can_search()

    def silent_services(self) -> Dict[str, float]:
        """The marks that still stand, for a caller that wants to say them out
        loud — the server prints them at startup so a household is told which
        of its services the app has stopped offering.

        Expired ones are left out rather than reported: only ``can_play``
        prunes them, so a server started a day later would otherwise announce
        a service the very next request is going to use happily."""
        now = self.now()
        return {k: v for k, v in self._silent_until.items() if v > now}

    # -- the two writes ----------------------------------------------------
    def _mark(self, key: str) -> None:
        if not key:
            return
        self._silent_until[key] = self.now() + self.PLAYBACK_MISS_TTL
        self._save()

    def _unmark(self, key: str) -> None:
        if self._silent_until.pop(key, None) is not None:
            self._save()
