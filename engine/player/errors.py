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
    """
