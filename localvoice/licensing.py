"""Pro license manager — Lemon Squeezy license keys, stdlib only.

Design goals, in order:

1. **Never brick.** ``is_pro()`` is a pure local check (cache file + env);
   the network is touched only on user-initiated activation and on an
   at-most-weekly background revalidation that downgrades **only** when
   Lemon Squeezy definitively answers ``valid: false`` (key disabled or
   refunded). Timeouts, DNS failures and 5xx change nothing: an offline
   household keeps what it paid for, forever.
2. **Honest by design.** The gate is trust-based: this module is AGPL, there
   is no obfuscation, and the docs say so. The key is how users support the
   project, not a lock to pick.
3. **Let people feel it first.** A free tier of typed commands never conveys
   what the app is for — the whole product is the moment you speak and the
   music starts. So every install opens a full-Pro window (14 days), and
   ``is_pro()`` has two sources of truth: a paid key, or that window still
   being open. Server-side, so the features gated on the server's CPU
   (``/transcribe``, ``/wakeword/chunk``) light up too, and so no amount of
   clearing browser storage re-arms it.

The Lemon Squeezy activate/validate endpoints need no API auth — just the
key itself — so nothing secret ships with the app.

The trial adds no network traffic at all: it is one timestamp in the data
directory, compared against the clock. Deleting that file restarts the window,
which is deliberate — a user with write access to their own data directory can
already edit ``license.json``, and pretending otherwise would mean obfuscation
this project has promised not to ship.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import appdata

API_BASE = "https://api.lemonsqueezy.com/v1/licenses"
REVALIDATE_AFTER = 7 * 24 * 3600  # seconds; at most one check per week
CACHE_FILE = "license.json"

DAY_SECONDS = 24 * 3600
TRIAL_DAYS = 14
# No build of this code existed before this instant, so a clock reading
# earlier than it is not a clock — it is a machine that has not found NTP yet.
# A Pi without an RTC boots at the fake-hwclock time (often 1970) and syncs a
# few seconds later: opening the window at that reading wrote a start date 56
# years in the past, and the very first page load said the trial had expired.
# Refuse to open the window until the clock is plausible; startup retries on
# the next request, and the systemd unit now waits for time-sync.target.
BUILD_EPOCH = 1_767_225_600  # 2026-01-01T00:00:00Z
# Kept apart from license.json rather than folded into it: the window opens
# before any key exists, and activating (or losing) a key must not disturb it.
TRIAL_FILE = "trial.json"

HttpPost = Callable[[str, Dict[str, str]], Tuple[int, Dict[str, Any]]]


def _http_post(url: str, fields: Dict[str, str],
               timeout: float = 10.0) -> Tuple[int, Dict[str, Any]]:
    """Form-encoded POST returning ``(status, parsed_json)``.

    4xx bodies are parsed too (Lemon Squeezy explains errors there);
    anything unparsable raises like a network failure would.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(url, data=data,
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            except ValueError:
                pass
        raise


class LicenseManager:
    def __init__(self, data_dir: str, api_base: str = API_BASE,
                 http_post: Optional[HttpPost] = None,
                 now: Callable[[], float] = time.time,
                 environ=os.environ, trial_days: int = TRIAL_DAYS) -> None:
        self.path = os.path.join(data_dir, CACHE_FILE)
        self.trial_path = os.path.join(data_dir, TRIAL_FILE)
        self.trial_days = trial_days
        self.api_base = api_base
        self.http_post = http_post or _http_post
        self.now = now
        self.environ = environ

    # -- local state (never touches the network) ----------------------------

    def _cache(self) -> Optional[Dict[str, Any]]:
        data = appdata.read_json(self.path)
        return data if isinstance(data, dict) and data.get("key") else None

    def is_pro(self) -> bool:
        if appdata.env("PRO", environ=self.environ) == "1":
            return True  # dev/test bypass, documented
        cache = self._cache()
        if cache and not cache.get("revoked"):
            return True
        # The second source of truth. Deliberately consulted even when a key
        # exists but was revoked: someone who refunded on day 3 keeps the
        # window they were already inside, which is what "never brick" means
        # here — the window closes on its own date, not on a refund.
        return self.trial_active()

    # -- the first-install trial window (local, no network) -----------------

    def _trial(self) -> Optional[Dict[str, Any]]:
        data = appdata.read_json(self.trial_path)
        if not isinstance(data, dict):
            return None
        started = data.get("started_at")
        return data if isinstance(started, (int, float)) else None

    def clock_is_plausible(self) -> bool:
        """False while the system clock reads earlier than this code existed
        (see BUILD_EPOCH) — i.e. before NTP has answered on an RTC-less box."""
        return self.now() >= BUILD_EPOCH

    def start_trial(self) -> bool:
        """Open the window, once per install. ``True`` if this call opened it.

        Called at startup rather than from a request handler, so the clock
        starts when the app is installed and no client can start (or restart)
        it. Idempotent: a window already open — or already expired — is left
        exactly as it is.

        Refuses to open one at all while the clock is implausible: a window
        stamped 1970 is born 56 years expired, and it is written once and
        never revisited. Better to open it a few seconds later, when the time
        is real.
        """
        if self._trial() is not None:
            return False
        if not self.clock_is_plausible():
            return False
        appdata.atomic_write_json(self.trial_path, {
            "started_at": int(self.now()),
            "days": self.trial_days,
        })
        return True

    def start_trial_async(self, sleep=time.sleep,
                          poll: float = 5.0, tries: int = 120):
        """Open the window as soon as the clock is worth trusting.

        Opens it right away on any machine whose time is already right —
        every one with an RTC — and returns ``(opened, None)``. On a board
        that boots pre-NTP it returns ``(False, thread)``: a daemon thread
        that keeps looking for up to ten minutes and opens the window the
        moment the time arrives, so a Pi is not left without a trial because
        it happened to start before its clock did.
        """
        if self.start_trial() or self._trial() is not None:
            return True, None
        if self.clock_is_plausible():
            return False, None      # refused for another reason; nothing to wait for

        def wait_for_the_clock() -> None:
            for _ in range(tries):
                sleep(poll)
                if self.start_trial():
                    return

        thread = threading.Thread(target=wait_for_the_clock, daemon=True)
        thread.start()
        return False, thread

    def _trial_elapsed(self) -> Optional[Tuple[float, int]]:
        """``(seconds since the window opened, its length in days)``, or None.

        Negative elapsed time is clamped to zero: a clock that jumped backwards
        (an RPi without an RTC finding NTP, say) must not shorten a window, and
        certainly must not read as expired.
        """
        trial = self._trial()
        if trial is None:
            return None
        days = trial.get("days")
        if not isinstance(days, int) or days <= 0:
            days = self.trial_days
        if not self.clock_is_plausible():
            # The clock is behind the epoch, so every arithmetic here is
            # meaningless. Report the window as freshly opened rather than
            # letting a 1970 reading expire it — the "never brick" rule.
            return 0.0, days
        return max(0.0, self.now() - trial["started_at"]), days

    def trial_active(self) -> bool:
        elapsed = self._trial_elapsed()
        return elapsed is not None and elapsed[0] < elapsed[1] * DAY_SECONDS

    def trial_status(self) -> Dict[str, Any]:
        """What the page needs to talk about the window honestly.

        ``day`` is 1-based and keeps counting after expiry — the in-flow
        upgrade prompt is timed off it, and it must not reset to zero on the
        day the window closes, which is exactly when that prompt matters most.
        """
        elapsed = self._trial_elapsed()
        if elapsed is None:
            return {"active": False, "expired": False, "day": 0,
                    "days_left": 0, "days": self.trial_days}
        seconds, days = elapsed
        remaining = days * DAY_SECONDS - seconds
        active = remaining > 0
        return {
            "active": active,
            "expired": not active,
            "day": int(seconds // DAY_SECONDS) + 1,
            # Rounded up, so the last partial day still reads "1 day left"
            # rather than "0 days left" while the mic is demonstrably working.
            "days_left": int(-(-remaining // DAY_SECONDS)) if active else 0,
            "days": days,
        }

    def status(self) -> Dict[str, Any]:
        """What the settings UI shows — the key is masked to its last 4."""
        cache = self._cache() or {}
        key = cache.get("key") or ""
        return {
            "pro": self.is_pro(),
            "key": ("****" + key[-4:]) if key else None,
            "instance": cache.get("instance_name"),
            "activated_at": cache.get("activated_at"),
            "revoked": bool(cache.get("revoked")),
            "trial": self.trial_status(),
        }

    # -- activation (user-initiated, requires the network once) -------------

    def activate(self, key: str) -> Dict[str, Any]:
        """Activate ``key`` against Lemon Squeezy and cache the result.

        Returns ``{"ok": True}`` or ``{"ok": False, "error": "network" |
        "invalid", "detail": ...}`` — never raises, never writes partial
        state on failure.
        """
        key = (key or "").strip()
        if not key:
            return {"ok": False, "error": "invalid", "detail": "empty key"}
        instance = socket.gethostname() or "vivavoce"
        try:
            status, body = self.http_post(
                self.api_base + "/activate",
                {"license_key": key, "instance_name": instance})
        except Exception as exc:
            return {"ok": False, "error": "network", "detail": str(exc)}
        if not body.get("activated"):
            return {"ok": False, "error": "invalid",
                    "detail": body.get("error") or f"HTTP {status}"}
        appdata.atomic_write_json(self.path, {
            "key": key,
            "instance_id": (body.get("instance") or {}).get("id"),
            "instance_name": instance,
            "activated_at": int(self.now()),
            "last_validated": int(self.now()),
            "revoked": False,
        }, mode=0o600)   # 0600: the license key is a secret
        return {"ok": True}

    # -- background revalidation (best-effort, never downgrades on errors) --

    def revalidate_async(self) -> Optional[threading.Thread]:
        """Weekly opportunistic re-check, in a daemon thread at startup."""
        if appdata.env("NO_REVALIDATE", environ=self.environ) == "1":
            return None
        cache = self._cache()
        if not cache or cache.get("revoked"):
            return None
        if self.now() - (cache.get("last_validated") or 0) < REVALIDATE_AFTER:
            return None
        thread = threading.Thread(target=self._revalidate, daemon=True)
        thread.start()
        return thread

    def _revalidate(self) -> None:
        cache = self._cache()
        if not cache:
            return
        try:
            _status, body = self.http_post(
                self.api_base + "/validate",
                {"license_key": cache["key"],
                 "instance_id": cache.get("instance_id") or ""})
        except Exception:
            return  # network trouble: change nothing, retry next week
        if body.get("valid") is False:
            # The ONLY downgrade path: Lemon Squeezy said the key is dead
            # (disabled or refunded). An enabled kid-safe blocklist keeps
            # being enforced regardless — see pro/kidsafe.
            cache["revoked"] = True
            appdata.atomic_write_json(self.path, cache, mode=0o600)
        elif body.get("valid") is True:
            cache["last_validated"] = int(self.now())
            appdata.atomic_write_json(self.path, cache, mode=0o600)
