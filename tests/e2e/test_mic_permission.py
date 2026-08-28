"""The microphone permission prompt, dismissed instead of answered.

Tapping *beside* the prompt rather than on it is the easiest mistake a user
can make with this app, and it used to end the session: the microphone went
dead for the life of the page. Tap after tap did nothing, no prompt ever came
back, and only reloading brought it back — which is the tell, because a reload
is precisely a new SpeechRecognition object.

Chrome's part is unusual and is what the fake below reproduces: a dismissed
prompt produces **no event at all** — no onstart, no onerror, no onend — and
leaves the recogniser in its starting state, where every later start() throws
InvalidStateError. mic.js swallowed that throw, so nothing downstream ever
learned the microphone had stopped working.
"""

# `stranded: true` is the dismissed prompt: start() returns, says nothing
# back, and poisons the object. abort() is the only way out, which is the
# whole point of the test — the page has to actually call it.
FAKE_DISMISSED_PROMPT = """
    window.__sr = { starts: 0, aborts: 0, stranded: true, live: null };
    class FakeSR {
      constructor() {
        this.continuous = false; this.lang = ""; this.maxAlternatives = 1;
        this.interimResults = false; this._on = false; this._stuck = false;
      }
      start() {
        window.__sr.starts++;
        if (this._stuck || this._on) {
          throw new DOMException("already started", "InvalidStateError");
        }
        if (window.__sr.stranded) { this._stuck = true; return; }
        this._on = true; window.__sr.live = this;
        setTimeout(() => { if (this.onstart) this.onstart(); }, 0);
      }
      abort() {
        window.__sr.aborts++;
        const was = this._stuck || this._on;
        this._stuck = false; this._on = false;
        if (was) setTimeout(() => { if (this.onend) this.onend(); }, 0);
      }
      stop() { this.abort(); }
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


def _open(page, srv):
    page.add_init_script(FAKE_DISMISSED_PROMPT)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")


def _listening(page):
    return page.eval_on_selector("#mic", "el => el.classList.contains('listening')")


def test_a_dismissed_prompt_does_not_kill_the_microphone(page, web):
    srv = web(license_mgr=_ProLicense())
    _open(page, srv)

    # First tap: the prompt goes up and the user taps beside it.
    page.click("#mic")
    page.wait_for_function("() => window.__sr.starts === 1", timeout=3000)
    assert not _listening(page), "nothing should be listening yet"

    # The browser would show the prompt again, and this time it is answered.
    page.evaluate("window.__sr.stranded = false")

    # Second tap. This is the one that used to do nothing at all.
    page.click("#mic")
    page.wait_for_function(
        "() => document.getElementById('mic').classList.contains('listening')",
        timeout=3000)
    assert page.evaluate("window.__sr.aborts") >= 1, (
        "the stranded session has to be aborted, or start() keeps throwing")


def test_the_recovery_survives_a_second_dismissal(page, web):
    """Dismissing twice is not rarer than dismissing once, and must not be
    the state the first recovery cannot get out of."""
    srv = web(license_mgr=_ProLicense())
    _open(page, srv)

    page.click("#mic")
    page.wait_for_function("() => window.__sr.starts >= 1", timeout=3000)
    page.click("#mic")
    page.wait_for_function("() => window.__sr.starts >= 2", timeout=3000)
    assert not _listening(page)

    page.evaluate("window.__sr.stranded = false")
    page.click("#mic")
    page.wait_for_function(
        "() => document.getElementById('mic').classList.contains('listening')",
        timeout=3000)


def test_a_denied_microphone_leaves_continuous_listening_alone(page, web):
    """A denial on tap-to-talk must not untick wake mode.

    It used to: the not-allowed branch tore down continuous listening
    whatever mode the error arrived in, so a prompt dismissed while tapping
    the microphone silently switched off a preference the user had set on
    purpose — and wrote that to localStorage, so it did not come back.
    """
    srv = web(license_mgr=_ProLicense())
    _open(page, srv)
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.evaluate("localStorage.setItem('wakemode', '1')")
    page.evaluate("""
        window.__sr.stranded = false;
        document.getElementById('mic').click();
    """)
    page.wait_for_function("() => !!window.__sr.live", timeout=3000)
    page.evaluate("window.__sr.live.onerror({ error: 'not-allowed' })")
    page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('not-allowed')",
        timeout=3000)
    assert page.evaluate("localStorage.getItem('wakemode')") == "1"
