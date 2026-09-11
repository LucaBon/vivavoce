"""What a client does when the music server is slow, flaky or off.

One spoken turn is several sequential round trips — search, play, then the
lookup that names what started. Each was individually bounded by the socket
timeout and nothing bounded the sum, so against a half-dead server a single
sentence sat there for twenty-odd seconds and then answered "unreachable";
against one simply switched off it did that again for the next sentence, and
the next.

Three answers, and none of them is specific to LMS: one retry (a dropped
packet is not an outage), a budget for the whole turn, and a breaker so that
"the hi-fi is off" is learned once rather than re-timed-out all evening. They
lived inside ``lms.py`` because there was one client; they are here because
every backend needs them and none of them should discover it the hard way.
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Callable

from .errors import PlayerError

#: Consecutive transport failures before a client stops dialling for a while.
#: Three, because one is noise (a dropped packet, a server mid-restart) and the
#: retry in :meth:`Resilient._guarded` already absorbs it.
BREAKER_THRESHOLD = 3

#: How long the breaker stays open. Long enough that a server which is simply
#: off stops costing a socket timeout per call, short enough that one turned
#: back on is noticed without touching the app.
BREAKER_COOLDOWN = 15.0


class Breaker:
    """Consecutive-failure counter that stops a dead server being re-dialled.

    A spoken turn issues several calls in a row — a search, then the play,
    then the now-playing lookup that names what started. With a server that is
    off, each one waits out the full socket timeout before failing, so "the
    music server is not answering" costs 8 seconds three or four times over
    and the listener hears nothing at all for half a minute. After
    ``threshold`` failures the next calls fail immediately instead, until
    ``cooldown`` has passed and one probe is allowed through.

    Shared by every shallow copy of a client (``for_service``/``for_player``),
    like the search-node cache and for the same reason: whether the music
    server is answering is a fact about the server, not about which clone
    asked.

    Note that the cooldown expiring does not reset the failure count — only a
    success does. So the probe that follows a cooldown is exactly one call: if
    it fails the breaker opens again at once, and a household that left the
    hi-fi off does not pay for the timeout twice a minute.
    """

    def __init__(self, threshold: int = BREAKER_THRESHOLD,
                 cooldown: float = BREAKER_COOLDOWN,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.now = now
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0

    def open_for(self) -> float:
        """Seconds until a call is worth making again; 0.0 when it is now."""
        with self._lock:
            return max(0.0, self._open_until - self.now())

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                self._open_until = self.now() + self.cooldown

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0


class Resilient:
    """Breaker + per-turn budget, for a client that calls one music server.

    A backend mixes this in, calls :meth:`_init_resilience` from its own
    ``__init__``, and routes every round trip through :meth:`_guarded`. What it
    owes in return is two attributes: ``_transport`` (the callable that makes
    the request) and ``error`` (the :class:`PlayerError` subclass it raises),
    so a failure arrives wearing the backend's own name.
    """

    #: The exception this client raises. Overridden per backend.
    error = PlayerError

    def _init_resilience(self, timeout: float) -> None:
        self.timeout = timeout
        # A mutable object rather than a counter attribute, because a shallow
        # copy (for_player/for_service) shares the object but would not share
        # a rebound attribute — and "the server is not answering" is a fact
        # about the server, not about which clone asked.
        self._breaker = Breaker()
        # Per-thread deadline for the current turn (see turn_deadline). One
        # Router is shared by every request on a conversation, so the budget
        # cannot live on the instance.
        self._turn = threading.local()

    @contextlib.contextmanager
    def turn_deadline(self, seconds: float):
        """Bound every call this thread makes to ``seconds`` in total.

        Inside this block a call gets whatever is left of the budget, never
        more, and once the budget is gone the remaining calls fail at once.
        The reply is then wrong-but-fast rather than wrong-but-slow, which is
        the only choice actually on offer.

        Nested blocks keep the tighter deadline: the budget of an outer turn
        is never extended by something it called.
        """
        previous = getattr(self._turn, "until", None)
        until = time.monotonic() + seconds
        self._turn.until = until if previous is None else min(previous, until)
        try:
            yield
        finally:
            self._turn.until = previous

    def _call_timeout(self) -> float:
        """The socket timeout for the next call: the configured one, clamped
        to what is left of the turn's budget (``timeout`` when unbounded)."""
        until = getattr(self._turn, "until", None)
        if until is None:
            return self.timeout
        return max(0.0, min(self.timeout, until - time.monotonic()))

    def _guarded(self, request):
        """One transport call, behind the breaker and with a single retry.

        Retried once, and only on a transport failure — a refused connection,
        a dropped socket, a server restarted mid-response. A well-formed answer
        we happen not to like is never retried: asking again gets the same
        answer, and the caller has already been told what it means.
        """
        wait = self._breaker.open_for()
        if wait > 0:
            raise self.error(
                f"music server not answering; not dialled again for {wait:.0f}s")
        if self._call_timeout() <= 0:
            raise self.error("request skipped: this turn ran out of time")
        try:
            result = self._transport(request)
        except self.error:
            # Retry only while the turn can still pay for a second attempt.
            if self._call_timeout() <= 0:
                self._breaker.record_failure()
                raise
            try:
                result = self._transport(request)
            except self.error:
                self._breaker.record_failure()
                raise
        self._breaker.record_success()
        return result
