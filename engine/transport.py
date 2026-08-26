"""The controls that do not need to resolve anything.

Pause, resume, skip, volume, the sleep timer, "what is playing", and the queue
as a whole. Every function here acts on the player in front of it and needs no
search, no candidates and no library — which is exactly what separates them
from the rest of the engine.
"""

from __future__ import annotations

from typing import Optional

from guard import Guard, is_blocked_item
from lms import LMSError
from matching import LIST_LIMIT, ActionResult, _label
from messages import msg

# One notch of the LMS volume scale (0-100) per spoken step.
VOLUME_STEP = 5

def pause(lms) -> ActionResult:
    try:
        lms.pause()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("paused"), ok=True)


def resume(lms) -> ActionResult:
    try:
        lms.resume()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("resumed"), ok=True)


def next_track(lms) -> ActionResult:
    try:
        lms.next_track()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("next_track"), ok=True)


def previous_track(lms) -> ActionResult:
    try:
        lms.previous_track()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("previous_track"), ok=True)


def change_volume(lms, direction: str) -> ActionResult:
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
    delta = VOLUME_STEP if direction == "up" else -VOLUME_STEP
    try:
        lms.volume(delta)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
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
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    key = "sleep_set_one" if minutes == 1 else "sleep_set"
    return ActionResult(msg(key, minutes=minutes), ok=True)


def cancel_sleep(lms) -> ActionResult:
    try:
        lms.sleep(0)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("sleep_cancelled"), ok=True)


def now_playing(lms) -> ActionResult:
    try:
        info = lms.now_playing_info()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
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


# -- queue (playlist) management -------------------------------------------
def clear_queue(lms) -> ActionResult:
    try:
        lms.clear_queue()
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    return ActionResult(msg("queue_cleared"), ok=True)


def queue_list(lms, limit: int = LIST_LIMIT, *, guard: Optional[Guard] = None) -> ActionResult:
    """Read back the next few tracks queued after the current one."""
    try:
        upcoming = lms.queue_upcoming(limit)
    except LMSError:
        return ActionResult(msg("err_unreachable"), ok=False)
    if guard and guard.restricted:  # never read a blocked title back aloud
        upcoming = [t for t in upcoming if not is_blocked_item(t, guard.blocklist)]
    if not upcoming:
        return ActionResult(msg("queue_empty"), ok=True)
    listing = ", ".join(
        msg("enum_item", n=i + 1, name=_label(t)) for i, t in enumerate(upcoming)
    )
    terms = [t["title"] for t in upcoming] + [t["artist"] for t in upcoming if t.get("artist")]
    return ActionResult(msg("queue_list", listing=listing), ok=True, terms=terms)
