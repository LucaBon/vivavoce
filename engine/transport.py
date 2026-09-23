"""The controls that do not need to resolve anything.

Pause, resume, skip, volume, the sleep timer, "what is playing", and the queue
as a whole. Every function here acts on the player in front of it and needs no
search, no candidates and no library — which is exactly what separates them
from the rest of the engine.
"""

from __future__ import annotations

from typing import Optional

from guard import Guard, is_blocked_item
from matching import LIST_LIMIT, ActionResult, _label, unreachable
from messages import msg
from player.errors import PlayerError

# One notch of the LMS volume scale (0-100) per spoken step.
VOLUME_STEP = 5

def pause(lms) -> ActionResult:
    try:
        lms.pause()
    except PlayerError:
        return unreachable()
    return ActionResult(msg("paused"), ok=True)


def resume(lms) -> ActionResult:
    try:
        lms.resume()
    except PlayerError:
        return unreachable()
    return ActionResult(msg("resumed"), ok=True)


def next_track(lms) -> ActionResult:
    try:
        lms.next_track()
    except PlayerError:
        return unreachable()
    return ActionResult(msg("next_track"), ok=True)


def previous_track(lms) -> ActionResult:
    try:
        lms.previous_track()
    except PlayerError:
        return unreachable()
    return ActionResult(msg("previous_track"), ok=True)


def change_volume(lms, direction: str) -> ActionResult:
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
    delta = VOLUME_STEP if direction == "up" else -VOLUME_STEP
    try:
        lms.volume(delta)
    except PlayerError:
        return unreachable()
    return ActionResult(msg("volume_up" if direction == "up" else "volume_down"),
                        ok=True)


# A sleep timer beyond half a day is a misheard number, not a request
# («spegni tra 100000 minuti» was armed as-is).
MAX_SLEEP_MINUTES = 12 * 60


def set_sleep(lms, minutes: int) -> ActionResult:
    """Arm the LMS sleep timer: playback stops after ``minutes``."""
    if not minutes or minutes <= 0:
        return ActionResult(msg("ask_sleep"), ok=False)
    minutes = int(minutes)
    if minutes > MAX_SLEEP_MINUTES:
        return ActionResult(msg("sleep_too_long", max=MAX_SLEEP_MINUTES),
                            ok=False)
    try:
        lms.sleep(minutes * 60)
    except PlayerError:
        return unreachable()
    key = "sleep_set_one" if minutes == 1 else "sleep_set"
    return ActionResult(msg(key, minutes=minutes), ok=True)


def cancel_sleep(lms) -> ActionResult:
    try:
        lms.sleep(0)
    except PlayerError:
        return unreachable()
    return ActionResult(msg("sleep_cancelled"), ok=True)


def now_playing(lms) -> ActionResult:
    try:
        info = lms.now_playing_info()
    except PlayerError:
        return unreachable()
    if not info or not info.get("title"):
        return ActionResult(msg("nothing_playing"), ok=True)
    # "status - 1" hands back the queue head whatever the transport is doing,
    # so a stopped player used to answer "Sta suonando X" about a song nobody
    # could hear. Paused says paused; stopped says nothing is playing. Only an
    # explicit mode contradicts the queue head — a transport that reports none
    # is taken at face value, as before.
    mode = info.get("mode")
    if mode == "stop":
        return ActionResult(msg("nothing_playing"), ok=True)
    prefix = "paused_on" if mode == "pause" else "now_playing"
    title = info.get("title")
    artist = info.get("artist")
    if artist:
        return ActionResult(
            msg(prefix + "_by", title=title, artist=artist),
            ok=True, terms=[title, artist],
        )
    return ActionResult(msg(prefix, title=title), ok=True, terms=[title])


# A jump beyond half a day is a misheard number, like MAX_SLEEP_MINUTES: no
# chapter is that long, and «avanti di 100000 secondi» is not a request.
MAX_SEEK_SECONDS = 12 * 60 * 60


def _span(seconds: int) -> str:
    """How far a jump went, said the way it was asked: minutes when it is a
    whole number of them, seconds otherwise."""
    if seconds == 60:
        return msg("span_one_minute")
    if seconds >= 60 and seconds % 60 == 0:
        return msg("span_minutes", n=seconds // 60)
    return msg("span_seconds", n=seconds)


def _seconds(value) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def seek_relative(lms, delta: int) -> ActionResult:
    """Jump ``delta`` seconds forward (positive) or back (negative) within
    what is playing — «vai avanti di 30 secondi», the command that tells a
    book from a song.

    Every system has only an *absolute* seek, so this reads where the track
    is and adds. Clamped to the start, and to one second short of the end
    when the track says how long it is: landing past the end would be a
    silent skip to the next chapter, which is not what «avanti» asked for.
    A backend that reports no duration (Music Assistant can say ``None``) is
    clamped at the start only and trusted with the rest.
    """
    delta = int(delta)
    if not delta or abs(delta) > MAX_SEEK_SECONDS:
        return ActionResult(msg("ask_seek"), ok=False)
    try:
        info = lms.status_info() or {}
        if info.get("mode") == "stop" or not info.get("title"):
            return ActionResult(msg("nothing_playing"), ok=True)
        target = _seconds(info.get("elapsed")) + delta
        duration = _seconds(info.get("duration"))
        if duration:
            target = min(target, max(0.0, duration - 1))
        lms.seek(max(0.0, target))
    except PlayerError:
        return unreachable()
    key = "seek_forward" if delta > 0 else "seek_back"
    return ActionResult(msg(key, span=_span(abs(delta))), ok=True)


# -- queue (playlist) management -------------------------------------------
def clear_queue(lms) -> ActionResult:
    try:
        lms.clear_queue()
    except PlayerError:
        return unreachable()
    return ActionResult(msg("queue_cleared"), ok=True)


def queue_list(lms, limit: int = LIST_LIMIT, *, guard: Optional[Guard] = None) -> ActionResult:
    """Read back the next few tracks queued after the current one."""
    try:
        upcoming = lms.queue_upcoming(limit)
    except PlayerError:
        return unreachable()
    if guard and guard.restricted:  # never read a blocked title back aloud
        upcoming = [t for t in upcoming if not is_blocked_item(t, guard.blocklist)]
    if not upcoming:
        return ActionResult(msg("queue_empty"), ok=True)
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=_label(t)) for i, t in enumerate(upcoming)
    )
    terms = [t["title"] for t in upcoming] + [t["artist"] for t in upcoming if t.get("artist")]
    return ActionResult(msg("queue_list", listing=listing), ok=True, terms=terms)
