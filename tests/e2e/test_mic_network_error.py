"""A speech-service failure must stay on screen, not vanish with the `end` event.

Edge (and Chrome) report an unreachable cloud recogniser as ``error: network``
and then, always, ``end``. mic.js wrote the error to the status line, and the
``end`` handler immediately overwrote it with "tap the microphone": the button
flipped back to idle a moment after the tap and the user saw no explanation —
it looked like the mic switched itself off.
"""

FAKE_NETWORK_FAILURE = """
    class FakeSR {
      constructor() { this.continuous = false; this.lang = ""; this._on = false; }
      start() {
        this._on = true;
        setTimeout(() => this.onstart && this.onstart(), 0);
        setTimeout(() => this.onerror && this.onerror({ error: "network" }), 30);
        setTimeout(() => { this._on = false; this.onend && this.onend(); }, 40);
      }
      stop() {}
      abort() {}
    }
    window.SpeechRecognition = FakeSR;
    window.webkitSpeechRecognition = FakeSR;
    localStorage.setItem('reclang', 'it');
    localStorage.setItem('pro_hint', '1');
"""


class _ProLicense:
    def is_pro(self):
        return True

    def status(self):
        return {"pro": True}


def test_network_error_is_still_shown_after_the_session_ends(page, web):
    srv = web(license_mgr=_ProLicense())
    page.add_init_script(FAKE_NETWORK_FAILURE)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")

    page.click("#mic")
    page.wait_for_timeout(400)  # error + end have both fired by now

    status = page.inner_text("#status")
    assert status.startswith("Microfono:"), status
    assert "servizio vocale" in status, status
    assert not page.eval_on_selector("#mic", "el => el.classList.contains('listening')")


class _FakeTranscriber:
    """Enough of the Whisper wrapper for /asr to say the engine is installed,
    and a record of what reached /transcribe."""

    model_name = "tiny"

    def __init__(self):
        self.calls = 0

    def available(self):
        return True

    def transcribe(self, audio, lang):
        self.calls += 1
        return {"text": "pausa", "alternatives": ["pausa"]}


def test_a_speech_service_that_cannot_be_reached_hands_the_tap_to_local_asr(
        page_with_fake_mic, web):
    # Edge answers every start() with `network` ~0.4 s later, on machines
    # where Chrome works fine: the mic lit up and went dark again on every
    # tap. With the server able to transcribe, that same tap must keep
    # listening — through local recognition — with nothing to configure.
    page = page_with_fake_mic
    transcriber = _FakeTranscriber()
    srv = web(license_mgr=_ProLicense(), transcriber=transcriber)
    page.add_init_script(FAKE_NETWORK_FAILURE)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    page.wait_for_function(
        "document.getElementById('localasrrow').style.display !== 'none'")
    assert not page.is_checked("#localasr")

    page.click("#mic")
    page.wait_for_timeout(600)  # error + end, then the recorder opens

    assert page.eval_on_selector("#mic", "el => el.classList.contains('listening')")
    assert "riconoscimento locale" in page.inner_text("#status")
    # Remembered, so the next tap skips the broken service altogether.
    assert page.is_checked("#localasr")
    assert page.evaluate("localStorage.getItem('localasr')") == "1"

    page.click("#mic")  # second tap stops and transcribes
    page.wait_for_function("!document.getElementById('mic').classList.contains('listening')")
    page.wait_for_timeout(500)
    assert transcriber.calls == 1


def test_without_local_asr_the_network_error_still_says_what_to_do(page, web):
    srv = web(license_mgr=_ProLicense())
    page.add_init_script(FAKE_NETWORK_FAILURE)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")

    page.click("#mic")
    page.wait_for_timeout(400)

    assert not page.is_checked("#localasr")
    assert "Chrome" in page.inner_text("#status")
