"""The free-text wake word on the browser engine (Web Speech), end to end.

The engine here is the one that has always existed: continuous Web Speech
recognition, matching whatever phrase the user typed in the settings panel.
Its sibling suite, ``test_wakeword_flow.py``, covers the server-side detector.

What makes this worth driving in a browser is the thing a unit test cannot
model: **Chrome ends a continuous session by itself every few seconds** and
the page restarts it. Everything that broke about the two-step flow ("say the
wake word, get asked for the command, say it") lived in that seam — the
command arrived in a session whose transcript no longer held the wake word.
So the fake recogniser below reproduces exactly that: cumulative result
snapshots, and a session that closes on its own after a silent stretch.
"""

# Chrome delivers continuous results as CUMULATIVE snapshots that grow entry
# by entry, and ends the session on its own after a pause. Both behaviours are
# the point of this fake; a recogniser that just echoed one transcript back
# would pass while the real one failed.
FAKE_CONTINUOUS_SPEECH = """
    window.__sr = { sessions: 0, live: null };
    const SESSION_MS = 1200;  // Chrome's own auto-stop, compressed
    class FakeSR {
      constructor() {
        this.continuous = false; this.lang = ""; this.maxAlternatives = 1;
        this.interimResults = false; this._on = false; this._acc = [];
      }
      start() {
        if (this._on) throw new DOMException("busy", "InvalidStateError");
        this._on = true; this._acc = [];
        window.__sr.sessions++; window.__sr.live = this;
        setTimeout(() => { if (this.onstart) this.onstart(); }, 0);
        this._auto = setTimeout(() => this._end(), SESSION_MS);
      }
      stop() { this._end(); }
      _end() {
        if (!this._on) return;
        this._on = false; clearTimeout(this._auto);
        setTimeout(() => { if (this.onend) this.onend(); }, 0);
      }
      // Test hook: fail the way a recogniser can after it has been stopped —
      // Chrome reports "aborted"/"network" on a session already on its way
      // out, and that arrives after whoever stopped it has moved on.
      failLater(error, delayMs) {
        setTimeout(() => {
          if (this.onerror) this.onerror({ error });
        }, delayMs);
      }
      // Test hook: one more heard phrase, delivered the cumulative way.
      say(text) {
        if (!this._on) return "SESSION_CLOSED";
        this._acc.push(text);
        const results = this._acc.map((t, i) => {
          const alt = { transcript: t };
          return Object.assign([alt], { isFinal: i === this._acc.length - 1,
                                        length: 1 });
        });
        if (this.onresult) this.onresult({ resultIndex: 0, results });
        clearTimeout(this._auto);
        this._auto = setTimeout(() => this._end(), SESSION_MS);
        return "ok";
      }
    }
    window.SpeechRecognition = FakeSR;
    window.webkitSpeechRecognition = FakeSR;
    localStorage.setItem('reclang', 'it');
    localStorage.setItem('source', 'auto');
    localStorage.setItem('pro_hint', '1');
"""


class _ProLicense:
    def is_pro(self):
        return True

    def status(self):
        return {"pro": True}


def _start_browser_wake(page, srv):
    """Boot the page into continuous listening on the Web Speech engine."""
    page.add_init_script(FAKE_CONTINUOUS_SPEECH)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.check("#wakemode")
    page.wait_for_function("() => window.__sr.sessions >= 1", timeout=5000)


def _say(page, text):
    return page.evaluate(f"window.__sr.live.say({text!r})")


def _wait_new_session(page):
    """Wait out one of Chrome's self-inflicted session restarts."""
    before = page.evaluate("window.__sr.sessions")
    page.wait_for_function(f"() => window.__sr.sessions > {before}", timeout=5000)
    page.wait_for_timeout(120)  # let onstart land


def _bubbles(page):
    return page.evaluate(
        "[...document.querySelectorAll('#log .bubble')].map(b => b.textContent)")


def test_wake_word_alone_then_command_in_a_later_session(page, web):
    # The two-step flow the panel advertises. It used to be dead on arrival:
    # the prompt appeared, Chrome recycled the session, and the command landed
    # in a transcript with no wake word in it — discarded without a word.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)

    assert _say(page, "vivavoce") == "ok"
    page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('Dimmi il comando')",
        timeout=3000)

    _wait_new_session(page)
    # The question must still stand: still asking, still visibly listening.
    assert "Dimmi il comando" in page.eval_on_selector("#status", "el => el.textContent")
    assert page.eval_on_selector("#mic", "el => el.classList.contains('listening')")

    assert _say(page, "pausa") == "ok"
    page.wait_for_function(
        "() => [...document.querySelectorAll('#log .bubble')]"
        "        .some(b => b.textContent === 'pausa')", timeout=5000)
    assert "pausa" in _bubbles(page)


def test_wake_word_alone_then_command_in_the_same_session(page, web):
    # The prompt answered promptly, before Chrome recycles anything. This
    # leaves two independent entries in one session — ["vivavoce", "pausa"] —
    # and the handler used to act on the LONGEST of them, which is the wake
    # word: the command was dropped and the panel simply asked again.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)

    _say(page, "vivavoce")
    page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('Dimmi il comando')",
        timeout=3000)
    assert _say(page, "pausa") == "ok"  # same session: no restart in between
    page.wait_for_function(
        "() => [...document.querySelectorAll('#log .bubble')]"
        "        .some(b => b.textContent === 'pausa')", timeout=5000)
    assert "pausa" in _bubbles(page)


def test_wake_word_and_command_in_one_breath_still_works(page, web):
    # The original grammar must survive the two-step one being added.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)

    _say(page, "vivavoce")
    _say(page, "vivavoce pausa")  # cumulative, the way Chrome grows a phrase
    page.wait_for_function(
        "() => [...document.querySelectorAll('#log .bubble')]"
        "        .some(b => b.textContent === 'pausa')", timeout=5000)
    # The wake word is stripped: what reaches /api/v1/command is the command alone.
    assert "pausa" in _bubbles(page)
    assert "vivavoce pausa" not in _bubbles(page)


def test_speech_without_the_wake_word_is_ignored(page, web):
    # The flip side of arming: a room talking near the microphone must not
    # have its conversation sent to the LMS as commands.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)

    _say(page, "passami il sale")
    page.wait_for_timeout(1800)  # well past the 1s command debounce
    assert _bubbles(page) == []
    assert "In ascolto" in page.eval_on_selector("#status", "el => el.textContent")


def test_the_question_is_answered_by_the_next_thing_said_only_once(page, web):
    # Arming is spent by the command it asked for: whatever is said after that
    # is ambient noise again, not a second command.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)

    _say(page, "vivavoce")
    page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('Dimmi il comando')",
        timeout=3000)
    _say(page, "pausa")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#log .bubble')]"
        "        .some(b => b.textContent === 'pausa')", timeout=5000)

    _wait_new_session(page)
    _say(page, "che bella giornata")
    page.wait_for_timeout(1800)
    assert "che bella giornata" not in _bubbles(page)


# --- "send right after the mic" and its coupling to wake mode --------------
#
# Hands-free listening whose transcript then waits in a box for a tap is not
# hands-free — you are across the room. So the toggle follows wake mode until
# the user says otherwise, and (unlike before) it remembers being said.

def _autosend(page):
    return page.eval_on_selector("#autosend", "el => el.checked")


def test_turning_on_wake_mode_turns_on_autosend(page, web):
    srv = web(license_mgr=_ProLicense())
    page.add_init_script(FAKE_CONTINUOUS_SPEECH)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    page.eval_on_selector("#settings", "el => { el.open = true; }")

    assert _autosend(page) is False
    page.check("#wakemode")
    assert _autosend(page) is True
    page.uncheck("#wakemode")
    assert _autosend(page) is False


def test_an_explicit_autosend_choice_outranks_wake_mode(page, web):
    # Untick it once and it stays unticked, however wake mode is toggled.
    srv = web(license_mgr=_ProLicense())
    page.add_init_script(FAKE_CONTINUOUS_SPEECH)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    page.eval_on_selector("#settings", "el => { el.open = true; }")

    page.check("#wakemode")
    page.uncheck("#autosend")  # the user has an opinion now
    page.uncheck("#wakemode")
    page.check("#wakemode")
    assert _autosend(page) is False

    # ...and it survives a reload, which it never used to: with nothing stored,
    # hands-free had to be re-armed by hand every time the app was opened.
    page.reload()
    page.wait_for_function("!!window.vivavoce")
    assert _autosend(page) is False
    assert page.eval_on_selector("#wakemode", "el => el.checked") is True


def test_autosend_off_leaves_the_wake_command_in_the_box(page, web):
    # The browser engine used to send unconditionally, so this checkbox did
    # nothing here while governing every other way of speaking.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)
    page.uncheck("#autosend")

    _say(page, "vivavoce pausa")
    page.wait_for_function(
        "() => document.getElementById('text').value === 'pausa'", timeout=5000)
    assert _bubbles(page) == [], "the command was sent despite auto-send being off"

    # The prompt has to outlive Chrome recycling the session, or the user is
    # told "listening…" while a transcript sits there waiting for them.
    _wait_new_session(page)
    status = page.eval_on_selector("#status", "el => el.textContent")
    assert "Controlla il testo" in status, f"prompt was clobbered: {status!r}"
    assert page.eval_on_selector("#text", "el => el.value") == "pausa"


def test_a_dead_sessions_error_does_not_overwrite_the_current_message(page, web):
    # One recogniser object is reused for every mode, so a late onerror carries
    # nothing saying which session it belongs to. Switching mode off tears the
    # live one down and settles the status line; the dying session then
    # reporting "aborted" would replace a correct message with an alarming one
    # about something the user has already left behind.
    srv = web(license_mgr=_ProLicense())
    _start_browser_wake(page, srv)
    dying = "window.__sr.live"

    page.uncheck("#wakemode")  # torn down on purpose; the status settles to idle
    settled = page.eval_on_selector("#status", "el => el.textContent")
    assert "Tocca il microfono" in settled, settled

    page.evaluate(f"{dying}.failLater('aborted', 10)")
    page.wait_for_timeout(300)
    assert page.eval_on_selector("#status", "el => el.textContent") == settled, (
        "an error from the session we killed replaced the current message")


def test_tap_to_talk_with_autosend_off_keeps_the_prompt(page, web):
    # Wake mode solved this with isAwaitingReview(); tap-to-talk never had the
    # equivalent, so handleManualFinal() wrote "check the text and press Send"
    # and the end of the capture immediately answered it with "tap the
    # microphone" — over a box silently waiting for Send.
    srv = web(license_mgr=_ProLicense())
    page.add_init_script(FAKE_CONTINUOUS_SPEECH)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    assert _autosend(page) is False  # wake mode is off, so this follows it

    page.click("#mic")  # one tap-to-talk shot
    # Wait for onstart, not merely for the session object: it writes the
    # status line itself, and a fake that answers before it lands is testing
    # an order the real recogniser never produces.
    page.wait_for_function(
        "() => document.getElementById('mic').classList.contains('listening')",
        timeout=5000)
    _say(page, "pausa")
    page.wait_for_function(
        "() => document.getElementById('text').value === 'pausa'", timeout=5000)

    # The session then ends the way Chrome ends one, which is where the
    # prompt used to be overwritten.
    page.wait_for_function("() => !window.__sr.live._on", timeout=5000)
    page.wait_for_timeout(200)
    status = page.eval_on_selector("#status", "el => el.textContent")
    assert "Controlla il testo" in status, f"prompt was clobbered: {status!r}"
    assert _bubbles(page) == []
