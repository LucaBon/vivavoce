"""What happens in the seconds AFTER a track is started.

Starting one is a single command; knowing whether it worked is not. A music
system takes the queue instantly and the audio follows later — or never, and
"never" is the case this module exists for.

``LMSClient.can_search`` already tells a connected service from a disconnected
one, and ``blocking_service`` acts on the same signal for the library rows a
streaming plugin imported. Between them they cover a plugin that is logged
OUT: one that answers its whole menu with an "authenticate in Settings"
notice, offers no search node, and is visibly unable to do anything. Neither
can see a plugin that is logged out of its AUDIO alone — which is what an
expired token looks like. That one keeps browsing and searching a catalogue it
is still allowed to read: the search comes back with the right track, the
right artist and a playable-looking url, and only the request for the audio
itself answers ``401``.

Nobody upstream can know this. The player can: it accepted the track and went
straight back to stop. So this module asks the player.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from lms import service_label
from matching import _normalize
from messages import msg
from player.errors import PlayerError

#: A play the music system ACCEPTED and the player never started. Its own kind
#: of failure, like ``library.IMPORT_OFFLINE``, because the answer it deserves
#: is not "I didn't find it": the music was found, and the plugin that owns the
#: audio cannot fetch it.
STREAM_OFFLINE = "stream_offline"

#: How long a stream gets to prove it is playing, in seconds.
#:
#: Measured against the real hi-fi (LMS 9.0.3, 2026-09-14): a ``tidal://`` url
#: whose token had expired read ``mode=play`` once and was back to ``stop``
#: 0.33s later, for good; a healthy ``qobuz://`` stream stayed ``mode=play``
#: and kept its elapsed time at zero for three whole seconds while it filled
#: its buffer. So the MODE is the signal and the elapsed time is not: over the
#: first seconds a stream that is buffering and one that is dead are the same
#: picture. This is the wait that tells them apart, and on the healthy path it
#: is spent with the music already playing.
PLAYBACK_SETTLE = 0.6

#: ``confirm_song``'s "nobody has asked the player yet", which is not the same
#: as having asked and got nothing.
UNREAD = object()


def after_play(lms) -> Tuple[Optional[str], Any]:
    """``(the service that stayed silent, the status reading)`` for a track
    just started with ``play_url``.

    The service is None when the track is playing, when the player cannot be
    asked — a hi-fi that stopped answering between the command and the
    question is a different fact, and must not be reported as this one — and
    when there is no service to name.

    That last case is why the name is worked out FIRST. The sentence this
    serves is «<service> is not connected»; a backend that cannot say which
    service it is aimed at has nothing to put in it, so it is not made to wait
    for an answer it could not use. It gets :data:`UNREAD` back and the
    confirmation reads the player itself, exactly as it always did.
    """
    service = service_label(getattr(getattr(lms, "service", None), "name", ""))
    if not service:
        return None, UNREAD
    time.sleep(PLAYBACK_SETTLE)
    try:
        now = lms.now_playing_info()
    except PlayerError:
        return None, None
    if not now or now.get("mode") != "stop":
        return None, now
    # Remembered on the client, not just reported: the next request should not
    # have to spend another silent play to learn the same thing, and the choice
    # of which service to ask is made with this in hand (``can_play``).
    lms.note_playback_failure()
    return service, now


def confirm_song(lms, track: Dict, fallback_title: Optional[str], now: Any = UNREAD):
    """Confirm what's playing, adding the artist when known. Returns
    ``(speech, terms)`` where terms are the foreign name(s) in the speech.

    TIDAL song-search items carry no artist, but the now-playing status does.
    ``now`` is the reading :func:`after_play` already took; :data:`UNREAD`
    means there is none and the player is asked here. Either way it is used
    only if the playing title matches what we just started — a guard against
    a status still showing the previous track.
    """
    name = track.get("title") or fallback_title
    artist = track.get("artist")
    if not artist and name:
        if now is UNREAD:
            try:
                now = lms.now_playing_info()
            except PlayerError:
                now = None
        if now and _normalize(now.get("title")) == _normalize(name):
            artist = now.get("artist")
    if artist:
        return msg("playing_by", name=name, artist=artist), [name, artist]
    return msg("playing", name=name), [name]
