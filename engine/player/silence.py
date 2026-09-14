"""The memory of a service that took a track and played none of it.

Written once and mixed into every backend, for the reason ``resilience.py``
gives about its own three: this is not a fact about LMS, it is a fact about
streaming plugins, and a backend should not have to discover it the hard way.

What it is for. A plugin that is logged OUT is visibly out — its menu is one
"authenticate in Settings" notice, it has no search node, and ``can_search``
catches it before anything is played. A plugin whose token has merely EXPIRED
looks perfect from the same distance: it browses, it searches, it hands back
the right track with a playable-looking url, and it refuses only the audio.
Nothing that can be asked before playing tells the two apart. What tells them
apart is a play that went nowhere (``engine/playback.py``), and the whole
value of that discovery is in not having to make it twice: it costs a queue
replaced, a room left silent, and the queue cleared again.

So the discovery is remembered here, and :meth:`can_play` is what the rest of
the app asks when it is choosing who to send a request to.
"""

from __future__ import annotations

import time
from typing import Dict

#: How long a service is taken at its word after playing nothing, in seconds.
#:
#: The arithmetic runs the opposite way to ``LMSClient.SEARCH_NODE_MISS_TTL``,
#: which is two seconds because forgetting a missing search node early costs
#: only a round trip. Forgetting THIS early costs another silent play on every
#: request, since searching still works and nothing else would stop it. A
#: minute spares the household that, and is short enough that someone who has
#: just logged the plugin back in is not told for much longer that it is out —
#: and naming the service out loud clears it at once in any case, which is the
#: case that actually matters (``forget_playback_failure``).
PLAYBACK_MISS_TTL = 60.0


class SilentServices:
    """``note_playback_failure`` / ``can_play`` for a client with services.

    The store is created in the client's ``__init__`` (``_init_silence``) and
    never rebound, so the shallow copies that ``for_service`` and
    ``for_player`` hand out SHARE it — "TIDAL plays nothing today" is a fact
    about the server, not about which clone asked. Same reasoning as the
    search-node cache and the breaker next door.
    """

    #: Overridable per backend, though no backend has had a reason to.
    PLAYBACK_MISS_TTL = PLAYBACK_MISS_TTL

    def _init_silence(self) -> None:
        self._silent_until: Dict[str, float] = {}

    def _service_key(self) -> str:
        """Which service the mark is about. The registry name, not the CLI
        tag: Spotify answers to ``spotty`` on an LMS and to ``spotify``
        everywhere else, and the fact being remembered is about Spotify."""
        return getattr(self.service, "name", "") or ""

    def note_playback_failure(self) -> None:
        """Remember that this service accepted a track and played none of it.
        Unaimed there is no service to blame, and nothing is remembered."""
        key = self._service_key()
        if key:
            self._silent_until[key] = time.monotonic() + self.PLAYBACK_MISS_TTL

    def forget_playback_failure(self) -> None:
        """Take the mark off: this service is being asked for on purpose."""
        self._silent_until.pop(self._service_key(), None)

    def can_play(self) -> bool:
        """Whether this service can be expected to deliver AUDIO right now.

        ``can_search`` asks the catalogue half of the plugin, and is the right
        question for "was anybody actually asked?"; this is the right question
        for "who should we ask?". They differ exactly when a token has expired
        — the case that used to be discovered one silent room at a time.
        """
        until = self._silent_until.get(self._service_key())
        if until is not None:
            if until > time.monotonic():
                return False
            del self._silent_until[self._service_key()]
        return self.can_search()
