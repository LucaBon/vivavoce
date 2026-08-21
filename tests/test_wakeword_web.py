"""Server-side wake-word HTTP endpoints: ``GET /wakeword``, ``POST
/wakeword/chunk``, ``POST /wakeword/stop``.

Mirrors test_transcribe.py's approach exactly: the session registry is
injectable on ``make_handler``, so these tests exercise the real HTTP stack
with a fake detector — no model, no ONNX runtime. Contract under test:
``/wakeword`` advertises availability; ``/wakeword/chunk`` never 5xxes
(unavailable / not-Pro / empty / too-large / engine failure all answer 200
with ``ok: false``); sessions are per-client and released on ``/stop``.
"""

from conftest import FakeLicense


class FakeDetector:
    def __init__(self, error=None):
        self.calls = []  # list of pcm bytes fed
        self.reset_calls = 0
        self.error = error
        self.next_triggered = False

    def process(self, pcm_bytes):
        self.calls.append(pcm_bytes)
        if self.error:
            raise self.error
        return self.next_triggered

    def reset(self):
        self.reset_calls += 1


class FakeSessions:
    """Stands in for ``pro.wakeword.ServerWakeWordSessions``."""

    model = "hey_jarvis"

    def __init__(self, available=True, error=None):
        self._available = available
        self.error = error
        self.detectors = {}  # client_id -> FakeDetector
        self.stopped = []

    def available(self):
        return self._available

    def get_or_create(self, client_id):
        det = self.detectors.get(client_id)
        if det is None:
            det = FakeDetector(error=self.error)
            self.detectors[client_id] = det
        return det

    def stop(self, client_id):
        self.stopped.append(client_id)
        self.detectors.pop(client_id, None)


PCM_CHUNK = (b"\x00\x00" * 1280)  # 80ms of 16-bit silence, the right shape


# -- GET /wakeword ---------------------------------------------------------

def test_wakeword_reports_available_with_model(live_server):
    srv = live_server(wakeword_sessions=FakeSessions())
    resp = srv.get("/wakeword")
    assert resp.status == 200
    assert resp.json() == {"available": True, "model": "hey_jarvis"}


def test_wakeword_reports_unavailable_without_sessions(live_server):
    srv = live_server(wakeword_sessions=None)
    assert srv.json_get("/wakeword") == {"available": False}


def test_wakeword_reports_unavailable_when_engine_missing(live_server):
    srv = live_server(wakeword_sessions=FakeSessions(available=False))
    assert srv.json_get("/wakeword") == {"available": False}


# -- POST /wakeword/chunk ---------------------------------------------------

def test_wakeword_chunk_reports_no_trigger(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions, license_mgr=FakeLicense(pro=True))
    resp = srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert resp.status == 200
    assert resp.json() == {"ok": True, "triggered": False}
    assert sessions.detectors["phone"].calls == [PCM_CHUNK]


def test_wakeword_chunk_reports_trigger_and_resets(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions, license_mgr=FakeLicense(pro=True))
    sessions.get_or_create("phone").next_triggered = True
    resp = srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert resp.json() == {"ok": True, "triggered": True}
    assert sessions.detectors["phone"].reset_calls == 1


def test_wakeword_chunk_keeps_separate_sessions_per_client(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions)
    srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    srv.post("/wakeword/chunk?client=tablet", PCM_CHUNK)
    assert set(sessions.detectors) == {"phone", "tablet"}


def test_wakeword_chunk_unavailable_answers_200(live_server):
    srv = live_server(wakeword_sessions=None)
    resp = srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert resp.status == 200
    assert resp.json() == {"ok": False, "error": "unavailable"}


def test_wakeword_chunk_engine_missing_answers_unavailable(live_server):
    srv = live_server(wakeword_sessions=FakeSessions(available=False))
    resp = srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert resp.json() == {"ok": False, "error": "unavailable"}


def test_wakeword_chunk_is_pro_gated_server_side(live_server):
    # Like /transcribe: hiding the toggle in the UI is not enforcement.
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions, license_mgr=FakeLicense(pro=False))
    resp = srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert resp.json() == {"ok": False, "error": "pro_required"}
    assert sessions.detectors == {}


def test_wakeword_chunk_empty_body_is_refused(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions)
    resp = srv.post("/wakeword/chunk?client=phone", b"")
    assert resp.json() == {"ok": False, "error": "empty"}
    assert sessions.detectors == {}


def test_wakeword_chunk_too_large_is_refused(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions)
    oversized = b"\x00" * (256 * 1024 + 1)
    resp = srv.post("/wakeword/chunk?client=phone", oversized)
    assert resp.json() == {"ok": False, "error": "too_large"}
    assert sessions.detectors == {}


def test_wakeword_chunk_engine_failure_answers_200(live_server):
    sessions = FakeSessions(error=RuntimeError("onnx blew up"))
    srv = live_server(wakeword_sessions=sessions)
    resp = srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert resp.status == 200
    data = resp.json()
    assert data["ok"] is False
    assert "onnx blew up" in data["error"]


def test_wakeword_chunk_defaults_client_id(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions)
    srv.post("/wakeword/chunk", PCM_CHUNK)  # no ?client=
    assert "default" in sessions.detectors


# -- POST /wakeword/stop -----------------------------------------------------

def test_wakeword_stop_releases_the_session(live_server):
    sessions = FakeSessions()
    srv = live_server(wakeword_sessions=sessions)
    srv.post("/wakeword/chunk?client=phone", PCM_CHUNK)
    assert "phone" in sessions.detectors
    resp = srv.post("/wakeword/stop?client=phone", b"")
    assert resp.status == 200
    assert resp.json() == {"ok": True}
    assert "phone" not in sessions.detectors
    assert sessions.stopped == ["phone"]


def test_wakeword_stop_without_sessions_is_a_noop(live_server):
    resp = live_server(wakeword_sessions=None).post("/wakeword/stop?client=phone", b"")
    assert resp.status == 200
    assert resp.json() == {"ok": True}


def test_wakeword_stop_unknown_client_is_a_noop(live_server):
    sessions = FakeSessions()
    resp = live_server(wakeword_sessions=sessions).post(
        "/wakeword/stop?client=never-started", b"")
    assert resp.json() == {"ok": True}
