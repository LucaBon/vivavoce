"""The one failure every backend speaks.

The engine has always turned "the music server did not answer" into a friendly
sentence rather than a traceback, and it recognised that situation by catching
``lms.LMSError``. That worked while there was one kind of music server. With
more than one it stops working for a reason worth stating plainly: a
``except LMSError`` does not catch a MusicAssistant failure, so the first
non-LMS backend would have crashed the turn instead of apologising for it.

So the engine catches :class:`PlayerError`, and every backend raises something
that derives from it. ``LMSError`` still exists and is still what the LMS
client raises — it is now a subclass, which is why every existing
``pytest.raises(LMSError)`` still means what it meant.
"""

from __future__ import annotations


class PlayerError(Exception):
    """The music server — whichever one — could not be reached or made sense of.

    Backends subclass this so a caller can still tell them apart when it has a
    reason to. The engine deliberately does not: for every action in
    ``engine/``, "the hi-fi is not answering" is one outcome with one reply.

    The client itself does care, though, and in two ways
    (``player/resilience.py``). Whether to open the breaker is a question
    about reachability, and a server that answered «no» has just proved it is
    there. Whether to try again is a question about whether the first attempt
    might have been carried out. So a backend raises one of the two kinds
    below where it knows which it is; a bare ``PlayerError`` is read as the
    cautious one, :class:`PlayerUnreachable`, possibly delivered.
    """


class PlayerUnreachable(PlayerError):
    """No answer came back: refused, timed out, dropped halfway.

    ``delivered`` says whether the request may have reached the server before
    it went quiet. False only when it certainly did not (the connection was
    refused, the name did not resolve): then anything may be sent again. True
    otherwise, and then only a request that is safe to repeat is — «volume
    +5» retried after a lost reply is +10.
    """

    def __init__(self, *args, delivered: bool = True) -> None:
        super().__init__(*args)
        self.delivered = delivered


def never_delivered(exc: BaseException) -> bool:
    """Whether a urllib/socket failure happened before the request was sent.

    A refused connection, a name that does not resolve, a network that is not
    there: the server never saw a byte, so anything may be sent again. Every
    other failure — a timeout, a reset, a reply cut short — may have come
    after the server acted.
    """
    import socket
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, (ConnectionRefusedError, socket.gaierror)) or (
        isinstance(reason, OSError) and getattr(reason, "errno", None) in
        _NOT_SENT_ERRNOS)


def _errnos(*names: str) -> frozenset:
    import errno
    return frozenset(getattr(errno, n) for n in names if hasattr(errno, n))


#: Failures that happen while connecting, before anything is written.
_NOT_SENT_ERRNOS = _errnos("ECONNREFUSED", "EHOSTUNREACH", "ENETUNREACH",
                           "EHOSTDOWN", "ENETDOWN")


class PlayerRefused(PlayerError):
    """An answer came back, and it was a refusal or made no sense.

    An HTTP error status, a rejected token, a body that is not the shape the
    client reads. Never retried — the same question gets the same answer —
    and never counted against the breaker: the server is plainly there.
    """
