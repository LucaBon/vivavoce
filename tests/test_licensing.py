"""Tests for the Pro license manager (localvoice/licensing.py).

The contract that matters commercially: activation caches locally and works
offline forever; the weekly revalidation downgrades ONLY on a definitive
``valid: false`` from Lemon Squeezy — never on network trouble; ``is_pro()``
never touches the network.
"""

import json
import urllib.request

import pytest

import appdata
from licensing import LicenseManager


class FakePost:
    """Scriptable http_post: queue outcomes per URL suffix."""

    def __init__(self):
        self.calls = []
        self.outcome = (200, {})

    def __call__(self, url, fields):
        self.calls.append((url, dict(fields)))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def post():
    return FakePost()


def mgr(tmp_path, post, now=lambda: 1_000_000, environ=None):
    return LicenseManager(str(tmp_path), api_base="https://ls.test/licenses",
                          http_post=post, now=now, environ=environ or {})


# -- activation ----------------------------------------------------------------

def test_activate_happy_path_writes_cache(tmp_path, post):
    post.outcome = (200, {"activated": True, "instance": {"id": "inst-1"}})
    m = mgr(tmp_path, post)
    assert m.activate("KEY-1234-ABCD") == {"ok": True}
    assert m.is_pro()
    cache = appdata.read_json(str(tmp_path / "license.json"))
    assert cache["key"] == "KEY-1234-ABCD"
    assert cache["instance_id"] == "inst-1"
    assert cache["revoked"] is False
    url, fields = post.calls[0]
    assert url.endswith("/activate")
    assert fields["license_key"] == "KEY-1234-ABCD"
    assert fields["instance_name"]  # hostname, whatever it is


def test_activate_invalid_key(tmp_path, post):
    post.outcome = (400, {"activated": False, "error": "license_key not found"})
    m = mgr(tmp_path, post)
    result = m.activate("WRONG")
    assert result["ok"] is False
    assert result["error"] == "invalid"
    assert "not found" in result["detail"]
    assert not m.is_pro()
    assert not (tmp_path / "license.json").exists()  # no partial state


def test_activate_network_down_leaves_no_state(tmp_path, post):
    post.outcome = OSError("dns failure")
    m = mgr(tmp_path, post)
    result = m.activate("KEY")
    assert result == {"ok": False, "error": "network", "detail": "dns failure"}
    assert not (tmp_path / "license.json").exists()


def test_activate_empty_key_rejected_without_network(tmp_path, post):
    m = mgr(tmp_path, post)
    assert m.activate("  ")["error"] == "invalid"
    assert post.calls == []


# -- is_pro / status ------------------------------------------------------------

def test_is_pro_env_bypass(tmp_path, post):
    env = {f"{appdata.PRIMARY_PREFIX}_PRO": "1"}
    assert mgr(tmp_path, post, environ=env).is_pro()
    assert post.calls == []  # pure local check


def test_status_masks_key(tmp_path, post):
    post.outcome = (200, {"activated": True, "instance": {"id": "i"}})
    m = mgr(tmp_path, post)
    m.activate("KEY-1234-ABCD")
    st = m.status()
    assert st["pro"] is True
    assert st["key"] == "****ABCD"
    assert "KEY-1234" not in json.dumps(st)


def test_status_unlicensed(tmp_path, post):
    # No key and no window opened: every field says so, and the trial block is
    # present but empty rather than absent — the page reads it unconditionally.
    st = mgr(tmp_path, post).status()
    assert st == {"pro": False, "key": None, "instance": None,
                  "activated_at": None, "revoked": False,
                  "trial": {"active": False, "expired": False, "day": 0,
                            "days_left": 0, "days": 14}}


# -- revalidation ---------------------------------------------------------------

def _activated(tmp_path, post, at=1_000_000):
    post.outcome = (200, {"activated": True, "instance": {"id": "i-1"}})
    m = mgr(tmp_path, post, now=lambda: at)
    m.activate("KEY-1234-ABCD")
    post.calls.clear()
    return m


def test_revalidate_skipped_when_fresh(tmp_path, post):
    m = _activated(tmp_path, post)
    m.now = lambda: 1_000_000 + 3600  # an hour later
    assert m.revalidate_async() is None
    assert post.calls == []


def test_revalidate_network_error_keeps_pro(tmp_path, post):
    m = _activated(tmp_path, post)
    m.now = lambda: 1_000_000 + 8 * 24 * 3600  # stale
    post.outcome = OSError("offline")
    thread = m.revalidate_async()
    thread.join(5)
    assert m.is_pro()  # offline never bricks


def test_revalidate_definitive_invalid_revokes(tmp_path, post):
    m = _activated(tmp_path, post)
    m.now = lambda: 1_000_000 + 8 * 24 * 3600
    post.outcome = (400, {"valid": False, "error": "license_key disabled"})
    thread = m.revalidate_async()
    thread.join(5)
    assert not m.is_pro()
    assert m.status()["revoked"] is True
    url, fields = post.calls[0]
    assert url.endswith("/validate")
    assert fields["instance_id"] == "i-1"


def test_revalidate_valid_refreshes_timestamp(tmp_path, post):
    m = _activated(tmp_path, post)
    later = 1_000_000 + 8 * 24 * 3600
    m.now = lambda: later
    post.outcome = (200, {"valid": True})
    m.revalidate_async().join(5)
    cache = appdata.read_json(str(tmp_path / "license.json"))
    assert cache["last_validated"] == later
    # A fresh timestamp means the next startup doesn't re-check.
    assert m.revalidate_async() is None


def test_revalidate_opt_out(tmp_path, post):
    m = _activated(tmp_path, post)
    m.now = lambda: 1_000_000 + 30 * 24 * 3600
    m.environ = {f"{appdata.PRIMARY_PREFIX}_NO_REVALIDATE": "1"}
    assert m.revalidate_async() is None
    assert post.calls == []


# -- HTTP endpoints --------------------------------------------------------------

def test_license_endpoints(tmp_path, post, lms):
    import threading
    from http.server import ThreadingHTTPServer

    import server as srv

    post.outcome = (200, {"activated": True, "instance": {"id": "i"}})
    m = mgr(tmp_path, post)
    handler = srv.make_handler(lms, "http://lms.local:9000/material/",
                               ["tidal"], "tidal", license_mgr=m)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/license", timeout=5) as r:
            assert json.loads(r.read())["pro"] is False
        req = urllib.request.Request(
            base + "/license",
            data=json.dumps({"key": "KEY-1234-ABCD"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read())
        assert body["ok"] is True
        assert body["pro"] is True
        assert body["key"] == "****ABCD"
        with urllib.request.urlopen(base + "/license", timeout=5) as r:
            assert json.loads(r.read())["pro"] is True
    finally:
        httpd.shutdown()


# -- the first-install trial window ----------------------------------------------
#
# The commercial point of the whole thing: a free tier of typed commands never
# lets anyone feel what the product is, so every install gets 14 days of full
# Pro. What has to be true is narrow and testable — it starts once, it is not
# a browser-side promise, it ends on its own date, and nothing breaks when it
# does.

DAY = 24 * 3600


def _clock(start=1_000_000):
    """A movable clock: ``now()`` reads it, ``at(days)`` moves it."""
    state = {"t": start}

    def now():
        return state["t"]

    now.at = lambda days: state.__setitem__("t", start + days * DAY)
    return now


def test_trial_is_not_open_until_it_is_started(tmp_path, post):
    # Constructing a manager must not open a window: the clock starts at
    # install (server startup calls start_trial), never as a side effect of
    # someone reading the license state.
    m = mgr(tmp_path, post)
    assert m.trial_active() is False
    assert m.is_pro() is False
    assert not (tmp_path / "trial.json").exists()


def test_started_trial_grants_pro_without_any_key(tmp_path, post):
    m = mgr(tmp_path, post)
    assert m.start_trial() is True
    assert m.is_pro() is True
    status = m.status()
    assert status["pro"] is True
    assert status["key"] is None  # Pro, but nobody paid: the UI must not
    assert status["trial"] == {"active": True, "expired": False, "day": 1,
                               "days_left": 14, "days": 14}


def test_trial_expires_on_its_own_date_and_breaks_nothing(tmp_path, post):
    now = _clock()
    m = mgr(tmp_path, post, now=now)
    m.start_trial()
    now.at(13.9)
    assert m.is_pro() is True
    assert m.trial_status()["days_left"] == 1  # a partial day still counts
    now.at(14)
    assert m.is_pro() is False
    status = m.status()
    assert status["trial"] == {"active": False, "expired": True, "day": 15,
                               "days_left": 0, "days": 14}
    # "Never brick": expiry is a state, not an error. Nothing raises, the
    # license panel still answers, and typed commands are untouched.
    assert status["revoked"] is False


def test_trial_starts_once_and_a_restart_does_not_re_arm_it(tmp_path, post):
    # The CA that matters: a window is one per installation. A second
    # start_trial() — every server restart makes one — must not extend it.
    now = _clock()
    m = mgr(tmp_path, post, now=now)
    assert m.start_trial() is True
    now.at(10)
    assert m.start_trial() is False
    assert m.trial_status()["days_left"] == 4
    now.at(20)
    assert m.start_trial() is False
    assert m.is_pro() is False


def test_trial_survives_a_restart(tmp_path, post):
    # A fresh manager over the same data dir is what a restart looks like.
    now = _clock()
    mgr(tmp_path, post, now=now).start_trial()
    now.at(3)
    reborn = mgr(tmp_path, post, now=now)
    assert reborn.is_pro() is True
    assert reborn.trial_status()["day"] == 4


def test_trial_day_number_keeps_counting_after_expiry(tmp_path, post):
    # The in-flow upgrade prompt is timed off `day` and must still fire once
    # the window has closed — which is exactly when asking makes most sense.
    now = _clock()
    m = mgr(tmp_path, post, now=now)
    m.start_trial()
    now.at(30)
    assert m.trial_status()["day"] == 31
    assert m.trial_status()["active"] is False


def test_trial_length_is_fixed_when_the_window_opens(tmp_path, post):
    # The length is written into the file, so changing TRIAL_DAYS later
    # neither extends nor cuts short a window somebody is already inside.
    now = _clock()
    LicenseManager(str(tmp_path), api_base="https://ls.test/licenses",
                   http_post=post, now=now, environ={},
                   trial_days=3).start_trial()
    later = LicenseManager(str(tmp_path), api_base="https://ls.test/licenses",
                           http_post=post, now=now, environ={},
                           trial_days=30)
    now.at(4)
    assert later.is_pro() is False
    assert later.trial_status()["days"] == 3


def test_trial_touches_no_network(tmp_path, post):
    now = _clock()
    m = mgr(tmp_path, post, now=now)
    m.start_trial()
    m.is_pro()
    m.status()
    now.at(20)
    m.is_pro()
    m.status()
    assert post.calls == []  # the whole point: no phone-home, ever


def test_a_backwards_clock_does_not_expire_a_trial(tmp_path, post):
    # A Raspberry Pi with no RTC boots in 1970 and jumps forward when NTP
    # answers; the reverse happens too. Neither may eat somebody's window.
    now = _clock()
    m = mgr(tmp_path, post, now=now)
    m.start_trial()
    now.at(-100)
    assert m.is_pro() is True
    assert m.trial_status()["days_left"] == 14


def test_a_paid_key_outlives_the_trial(tmp_path, post):
    now = _clock()
    post.outcome = (200, {"activated": True, "instance": {"id": "i"}})
    m = mgr(tmp_path, post, now=now)
    m.start_trial()
    m.activate("KEY-1234-ABCD")
    now.at(40)
    assert m.is_pro() is True
    assert m.status()["key"] == "****ABCD"
    assert m.status()["trial"]["expired"] is True


def test_an_open_window_outlives_a_revoked_key(tmp_path, post):
    # Refunding on day 3 does not close a window that is open on its own
    # terms; it closes on its date, like everyone else's.
    now = _clock()
    post.outcome = (200, {"activated": True, "instance": {"id": "i"}})
    m = mgr(tmp_path, post, now=now)
    m.start_trial()
    m.activate("KEY-1234-ABCD")
    post.outcome = (200, {"valid": False})
    m._revalidate()
    assert m.status()["revoked"] is True
    assert m.is_pro() is True   # still inside the window
    now.at(14)
    assert m.is_pro() is False  # and out of it when it ends


def test_corrupt_trial_file_is_ignored_not_fatal(tmp_path, post):
    # Same fail-open rule as the license cache: a truncated write degrades to
    # "no window", never to a stack trace on startup.
    (tmp_path / "trial.json").write_text("{not json", encoding="utf-8")
    m = mgr(tmp_path, post)
    assert m.trial_active() is False
    assert m.trial_status()["day"] == 0
    assert m.start_trial() is True  # and a fresh one can still open
    assert m.is_pro() is True
