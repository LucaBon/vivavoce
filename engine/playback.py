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

from matching import ActionResult, _normalize
from messages import msg
from player.errors import PlayerError
from player.protocols import service_label

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

#: How many tracks a queue may pass through, with not a second of any of them
#: played, before it is walking rather than starting.
#:
#: Measured on the real hi-fi the same day: an artist's twenty tracks on a
#: plugin whose token had expired marched from index 0 to index 19 with the
#: elapsed time never leaving zero, one 401 every ~170ms. So at
#: :data:`PLAYBACK_SETTLE` the queue is three or four tracks in and the mode
#: is still «play», because the walk has not finished yet — which is why the
#: mode alone, enough for one track, says nothing here. A single track never
#: reaches this: with nowhere to walk to, that player is at stop in 0.33s.
#:
#: Two, not one, deliberately. An artist's top track that is unplayable on its
#: own — the rights lapsed in one country, which happens — advances the queue
#: by one and then plays, and blaming the whole service for that would be a
#: worse lie than the one this exists to stop. Two in a row at the head of a
#: queue is not bad luck.
WALKED_AWAY = 2

#: ``confirm_song``'s "nobody has asked the player yet", which is not the same
#: as having asked and got nothing.
UNREAD = object()


def _walked_away(now: Dict[str, Any]) -> bool:
    """The queue has left the track we started and played none of it.

    The multi-track shape of the same silence: the player is still «play»,
    because it has more tracks to fail, and the elapsed time has never moved.
    """
    return (now.get("index") or 0) >= WALKED_AWAY and not (now.get("elapsed") or 0)


def after_play(lms) -> Tuple[Optional[str], Any]:
    """``(the service that stayed silent, the status reading)`` for a track
    just started with ``play_url``.

    Silent means one of two shapes, and the second one cost a second incident:
    a single track leaves the player at stop, while a queue of twenty walks
    through itself failing every one of them, mode «play» all the way down
    (:func:`_walked_away`).

    The service is None when the track is playing, when the player cannot be
    asked — a hi-fi that stopped answering between the command and the
    question is a different fact, and must not be reported as this one — and
    when there is no service to name.

    That last case is why the name is worked out FIRST. The sentence this
    serves is «<service> is not connected»; a backend that cannot say which
    service it is aimed at has nothing to put in it, so it is not made to wait
    for an answer it could not use. It gets :data:`UNREAD` back and the
    confirmation reads the player itself, exactly as it always did.

    The name comes off the client and not out of a table kept here: which
    words a music system uses for its own services are its own, and a table
    belonging to one of them names the others wrong or not at all — see
    ``player.protocols.service_label``.
    """
    service = service_label(lms)
    if not service:
        return None, UNREAD
    time.sleep(PLAYBACK_SETTLE)
    try:
        now = lms.now_playing_info()
    except PlayerError:
        return None, None
    if not now or not (now.get("mode") == "stop" or _walked_away(now)):
        # Nothing wrong so far, which is not the same as audio: a player that
        # says «play» and never advances looks like this too. Leave it for the
        # next request to settle (player/silence.py::settle_pending).
        if now:
            lms.note_playback_started()
        return None, now
    # Remembered on the client, not just reported: the next request should not
    # have to spend another silent play to learn the same thing, and the choice
    # of which service to ask is made with this in hand (``can_play``).
    lms.note_playback_failure()
    return service, now


def undo_play(lms) -> None:
    """Stop and empty what we just started. ``mode="play"`` replaces the queue,
    so this only ever undoes our own action — used when what started turns out
    to be blocked, and when it turns out to be silent."""
    try:
        lms.clear_queue()
    except PlayerError:
        pass


def started(lms, confirmation: ActionResult) -> ActionResult:
    """``confirmation``, unless what was just started never began to play —
    then the service's own bad news, and the queue is taken back.

    The convenience form of :func:`after_play` for the callers that start
    something and have no use for the status reading: an album, a playlist, an
    artist's twenty tracks. The song path reads it for the artist and so calls
    ``after_play`` directly.

    For a start aimed at a STREAMING service only. The local library must not
    come through here: a client is always aimed at some service, so a local
    file that would not play — a disk asleep, a row whose file is gone — would
    be reported as that service being disconnected, which is a lie about a
    service nobody asked anything. What covers the library is
    ``blocking_service``, which knows which service each row's audio belongs
    to because the url says so.
    """
    silent, _ = after_play(lms)
    if not silent:
        return confirmation
    undo_play(lms)
    return ActionResult(msg("service_not_connected", service=silent),
                        ok=False, kind=STREAM_OFFLINE)


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
