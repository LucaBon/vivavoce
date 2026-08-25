"""Local speech recognition endpoints: ``GET /asr`` and ``POST /transcribe``.

The transcriber is injectable on ``make_handler`` (like ``artwork_fetch``), so
these tests exercise the real HTTP stack with a fake engine — no model, no
download. Contract under test: ``/asr`` advertises availability; ``/transcribe``
never 5xxes (unavailable / not-Pro / empty / engine failure all answer 200 with
``ok: false``), forwards the audio bytes and the ``lang`` query param to the
engine, and passes the alternatives through for the /command mechanism.
"""

from conftest import FakeLicense
from pro.asr import MIN_RAM_GIB, default_model, total_ram_gib


class FakeTranscriber:
    model_name = "small"

    def __init__(self, available=True, result=None, error=None):
        self.calls = []  # list of (audio_bytes, lang)
        self._available = available
        self.result = result if result is not None else {
            "text": "metti la radio",
            "alternatives": ["metti la radio", "metti la ratio"],
        }
        self.error = error

    def available(self):
        return self._available

    def transcribe(self, audio, lang="it"):
        self.calls.append((audio, lang))
        if self.error:
            raise self.error
        return self.result


# The blob MediaRecorder sends; the handler reads the body, not the type.
AUDIO_TYPE = "audio/webm"


# -- GET /asr ------------------------------------------------------------------

def test_asr_reports_available_with_model(live_server):
    srv = live_server(transcriber=FakeTranscriber())
    resp = srv.get("/asr")
    status, data = resp.status, resp.json()
    assert status == 200
    assert data == {"available": True, "model": "small"}


def test_asr_reports_unavailable_without_transcriber(live_server):
    srv = live_server(transcriber=None)
    assert srv.json_get("/asr") == {"available": False}


def test_asr_reports_unavailable_when_engine_missing(live_server):
    # Transcriber wired but faster-whisper not installed: same answer.
    srv = live_server(transcriber=FakeTranscriber(available=False))
    assert srv.json_get("/asr") == {"available": False}


# -- POST /transcribe ----------------------------------------------------------

def test_transcribe_returns_text_and_alternatives(live_server):
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake, license_mgr=FakeLicense(pro=True))
    resp = srv.post("/transcribe?lang=en", b"OPUSDATA", AUDIO_TYPE)
    status, data = resp.status, resp.json()
    assert status == 200
    assert data == {"ok": True, "text": "metti la radio",
                    "alternatives": ["metti la radio", "metti la ratio"]}
    # The engine got the raw audio and the language from the query string.
    assert fake.calls == [(b"OPUSDATA", "en")]


def test_transcribe_defaults_to_italian(live_server):
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake)
    srv.post("/transcribe", b"AUDIO", AUDIO_TYPE)
    assert fake.calls[0][1] == "it"


def test_transcribe_unavailable_answers_200(live_server):
    srv = live_server(transcriber=None)
    resp = srv.post("/transcribe", b"AUDIO", AUDIO_TYPE)
    status, data = resp.status, resp.json()
    assert status == 200
    assert data == {"ok": False, "error": "unavailable"}


def test_transcribe_engine_missing_answers_unavailable(live_server):
    fake = FakeTranscriber(available=False)
    srv = live_server(transcriber=fake)
    assert srv.post("/transcribe", b"AUDIO", AUDIO_TYPE).json() == {
        "ok": False, "error": "unavailable"}
    assert fake.calls == []  # never reaches the engine


def test_transcribe_is_pro_gated_server_side(live_server):
    # Like kid-safe: hiding the toggle in the UI is not enforcement — a free
    # install must not burn server CPU on /transcribe.
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake, license_mgr=FakeLicense(pro=False))
    resp = srv.post("/transcribe", b"AUDIO", AUDIO_TYPE)
    status, data = resp.status, resp.json()
    assert status == 200
    assert data == {"ok": False, "error": "pro_required"}
    assert fake.calls == []


def test_transcribe_empty_body_is_refused(live_server):
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake)
    resp = srv.post("/transcribe", b"", AUDIO_TYPE)
    status, data = resp.status, resp.json()
    assert status == 200
    assert data == {"ok": False, "error": "empty"}
    assert fake.calls == []


def test_transcribe_oversized_body_is_refused(live_server):
    # The 15 MB cap: a spoken command is seconds long, so anything past it is
    # a runaway or a bomb, and must be refused without ever reaching the
    # engine. The wake-word endpoint's own cap has always been tested; this
    # one shares its guard now, and an untested half of a shared guard is how
    # a cap quietly stops being one.
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake)
    oversized = b"\x00" * (15 * 1024 * 1024 + 1)
    resp = srv.post("/transcribe", oversized, AUDIO_TYPE)
    assert resp.status == 200
    assert resp.json() == {"ok": False, "error": "too_large"}
    assert fake.calls == []


def test_transcribe_garbage_audio_answers_200(live_server):
    # Whatever blows up inside the engine (corrupt container, decode error)
    # must come back as ok:false, never as a 5xx.
    fake = FakeTranscriber(error=RuntimeError("cannot decode"))
    srv = live_server(transcriber=fake)
    resp = srv.post("/transcribe", b"not really audio", AUDIO_TYPE)
    status, data = resp.status, resp.json()
    assert status == 200
    assert data["ok"] is False
    assert "cannot decode" in data["error"]


def test_transcribe_alternatives_fall_back_to_text(live_server):
    # An engine with no n-best (Whisper) still feeds the /command mechanism:
    # the single transcript becomes the one-element alternatives list.
    fake = FakeTranscriber(result={"text": "pausa", "alternatives": []})
    srv = live_server(transcriber=fake)
    resp = srv.post("/transcribe", b"AUDIO", AUDIO_TYPE)
    _status, data = resp.status, resp.json()
    assert data == {"ok": True, "text": "pausa", "alternatives": ["pausa"]}


def test_transcribe_silence_gives_ok_empty(live_server):
    fake = FakeTranscriber(result={"text": "", "alternatives": []})
    srv = live_server(transcriber=fake)
    resp = srv.post("/transcribe", b"AUDIO", AUDIO_TYPE)
    _status, data = resp.status, resp.json()
    assert data == {"ok": True, "text": "", "alternatives": []}


# -- RAM-aware default model ---------------------------------------------------

def test_default_model_is_ram_aware():
    # Measured on the Italian fixtures: tiny/base mangle English song titles,
    # and small (~1 GB peak) doesn't fit a 2 GB box next to OS + LMS — so
    # below the threshold the default is OFF (an explicit --asr-model still
    # wins, upstream of this function).
    assert default_model(8.0) == "small"
    assert default_model(3.8) == "small"   # a real-world "4 GB" machine
    assert default_model(2.0) is None
    assert default_model(MIN_RAM_GIB - 0.1) is None
    # Unknown RAM (probe failed) must not cripple a capable machine.
    assert default_model(0.0) == "small"


def test_total_ram_probe_is_plausible():
    gib = total_ram_gib()
    assert 0.0 <= gib < 4096  # 0.0 = unknown is acceptable, garbage is not


# -- the trial window, where it is actually enforced ---------------------------
#
# The one enforcement claim in T0.1 that is real rather than trust-based:
# /transcribe spends the server's CPU, so it is gated server-side, and the
# trial window has to open and close that gate for real. A real
# LicenseManager, not the FakeLicense used above — the point is the window,
# and a fake would only prove that a boolean works.

def _trial_license(tmp_path, days_in=0.0):
    """A real manager whose window opened ``days_in`` days ago."""
    from licensing import LicenseManager
    opened = 1_000_000
    mgr = LicenseManager(str(tmp_path), http_post=None, now=lambda: opened,
                         environ={})
    mgr.start_trial()
    mgr.now = lambda: opened + days_in * 24 * 3600
    return mgr


def test_transcribe_works_inside_the_trial_window(live_server, tmp_path):
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake,
                      license_mgr=_trial_license(tmp_path, days_in=3))
    data = srv.post("/transcribe", b"AUDIO", AUDIO_TYPE).json()
    assert data["ok"] is True
    assert data["text"] == "metti la radio"
    assert fake.calls  # the engine really ran: no key, still Pro


def test_transcribe_is_refused_once_the_trial_window_closes(live_server,
                                                            tmp_path):
    # The line the whole free tier rests on. Fourteen days in, with no key,
    # a POST here must cost the server nothing.
    fake = FakeTranscriber()
    srv = live_server(transcriber=fake,
                      license_mgr=_trial_license(tmp_path, days_in=14))
    resp = srv.post("/transcribe", b"AUDIO", AUDIO_TYPE)
    assert resp.status == 200
    assert resp.json() == {"ok": False, "error": "pro_required"}
    assert fake.calls == []
