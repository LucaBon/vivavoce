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


def _wait_visible(page, selector, timeout_ms=5000, interval_ms=100):
    """Poll ``getComputedStyle(el).display`` rather than a CSS attribute
    selector: the inline style Playwright serializes for `el.style.display =
    ""` doesn't reliably contain a literal "display: none" substring to
    negate, so a `:not([style*='display: none'])` locator can silently never
    resolve even once the element is genuinely visible."""
    for _ in range(max(1, timeout_ms // interval_ms)):
        if page.eval_on_selector(selector, "el => getComputedStyle(el).display") != "none":
            return
        page.wait_for_timeout(interval_ms)
    raise AssertionError(f"{selector} never became visible within {timeout_ms}ms")


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
    _wait_visible(page, "#serverwakerow")

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


def test_server_wake_error_message_is_not_clobbered(page, web):
    # getUserMedia rejects (permission denied, no device, ...): the reported
    # error must survive being the LAST thing the user sees, not get
    # immediately overwritten by stopServerWake()'s generic idle text in the
    # same synchronous callback.
    page.add_init_script("""
        navigator.mediaDevices.getUserMedia = () =>
            Promise.reject(new DOMException('denied by test', 'NotAllowedError'));
    """)
    sessions = FakeSessions()
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    _wait_visible(page, "#serverwakerow")

    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.check("#wakemode")
    page.check("#serverwake")
    page.click("#mic")

    status = page.locator("#status")
    for _ in range(20):
        if "denied by test" in status.inner_text():
            break
        page.wait_for_timeout(100)
    assert "denied by test" in status.inner_text(), (
        f"error message was clobbered; status shows {status.inner_text()!r}")


def test_wakemode_preference_restored_without_web_speech(page_with_fake_mic, web):
    # Without Web Speech (e.g. Firefox), the wakemode checkbox restore used to
    # live only inside the Web-Speech branch: a saved "wakemode": "1"
    # preference silently reset to unchecked on every reload, even though
    # server-side wake word never needed Web Speech to work.
    page = page_with_fake_mic
    page.add_init_script("""
        delete window.SpeechRecognition;
        delete window.webkitSpeechRecognition;
        localStorage.setItem('wakemode', '1');
        localStorage.setItem('reclang', 'it');
        localStorage.setItem('source', 'auto');
        // applyPro() resets #wakemode to unchecked while not Pro (the
        // offline-first localStorage hint, checked before /license resolves)
        // — set it so this test observes the restore, not that reset.
        localStorage.setItem('pro_hint', '1');
    """)
    sessions = FakeSessions()
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    _wait_visible(page, "#serverwakerow")
    assert page.eval_on_selector("#wakemode", "el => el.checked") is True


