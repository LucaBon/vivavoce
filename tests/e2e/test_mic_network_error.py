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
