"""Server-side wake word (T2.3): the browser-capture wiring, for real.

This is the one place worth driving actual WebAudio machinery in a real
browser rather than a fake detector: it proves the capture graph
(getUserMedia -> ScriptProcessorNode -> resample -> Int16 PCM -> fetch) is
wired correctly end-to-end against the real running HTTP server. What it
CANNOT prove — because Chromium's fake media device produces synthetic
silence, never a real spoken phrase — is that "hey jarvis" is actually
detected reliably, or the roadmap's latency/no-beep claims on real Android
hardware; only real hardware in the user's hands can confirm those.

The wake-word model itself is faked (no openwakeword install needed here);
everything else — the page, the endpoints, the audio graph — is real.
"""


class _ProLicense:
    def is_pro(self):
        return True

    def status(self):
        return {"pro": True}


class FakeDetector:
    def process(self, pcm_bytes):
        return False  # silence never triggers; that's the point of this test

    def reset(self):
        pass


class FakeSessions:
    """Stands in for pro.wakeword.ServerWakeWordSessions, wired straight into
    the real live_server so the test observes real HTTP traffic, not a
    page.route stub."""

    model = "hey_jarvis"

    def __init__(self):
        self.chunk_calls = 0
        self.stopped = []

    def available(self):
        return True

    def get_or_create(self, client_id):
        self.chunk_calls += 1
        return FakeDetector()

    def stop(self, client_id):
        self.stopped.append(client_id)


def test_server_wake_word_streams_audio_and_stops_cleanly(page_with_fake_mic, web):
    page = page_with_fake_mic
    sessions = FakeSessions()
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")

    # The row is hidden until GET /wakeword resolves and reports availability.
    page.wait_for_selector("#serverwakerow:not([style*='display: none'])")

    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.check("#wakemode")
    page.check("#serverwake")
    page.click("#mic")

    # A real audio graph is now feeding real fetch() calls to the real server;
    # give it a moment to post at least a couple of chunks.
    page.wait_for_function("() => true", timeout=100)  # let one event loop tick pass
    for _ in range(20):
        if sessions.chunk_calls >= 2:
            break
        page.wait_for_timeout(150)
    assert sessions.chunk_calls >= 2, "no /wakeword/chunk traffic observed"
    assert page.eval_on_selector("#mic", "el => el.classList.contains('listening')")

    page.click("#mic")  # stop
    for _ in range(20):
        if sessions.stopped:
            break
        page.wait_for_timeout(100)
    assert sessions.stopped, "/wakeword/stop was never called"
    assert not page.eval_on_selector(
        "#mic", "el => el.classList.contains('listening')")
