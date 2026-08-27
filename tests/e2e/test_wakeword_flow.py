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
    # No tap on the mic button to get started: since the engine choice began
    # applying immediately, ticking the boxes IS what starts the stream, and a
    # tap here would toggle it straight back off — but only when getUserMedia
    # had already resolved by then, so this passed on the machines that lost
    # that race and failed on the ones that won it. It is a stop control here,
    # nothing more, and the test says so by using it only at the end.
    _start_server_wake(page, srv)

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
    page.check("#serverwake")  # this is what tries to open the microphone

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




# --- The hand-off between the wake stream and the command capture ----------
#
# Everything below exercises what happens AFTER a trigger fires, which is
# where server-side wake word was unusable in the field: the phrase was
# detected, and then nothing said after it was ever understood, while the mic
# button went dark as if listening had stopped.

FAKE_SPEECH_RECOGNITION = """
    // A scriptable stand-in for Web Speech: headless Chromium ships an
    // interface that never produces results, and these tests need to drive
    // start/end/result precisely rather than hope.
    // mic.js reconfigures ONE recogniser between continuous (its own wake
    // mode) and one-shot (the capture after a server-side trigger), so the
    // counters are split by that: a stop during an engine switch must not
    // look like the capture being cancelled.
    window.__sr = { starts: 0, stops: 0, live: null, continuous: null,
                    captureStarts: 0, captureStops: 0 };
    class FakeSR {
      constructor() {
        this.continuous = false; this.lang = ""; this.maxAlternatives = 1;
        this.interimResults = false; this._running = false;
      }
      start() {
        if (this._running) {
          throw new DOMException("already started", "InvalidStateError");
        }
        this._running = true;
        window.__sr.starts++;
        if (!this.continuous) window.__sr.captureStarts++;
        window.__sr.live = this;
        window.__sr.continuous = this.continuous;
        setTimeout(() => { if (this.onstart) this.onstart(); }, 0);
      }
      stop() {
        if (!this._running) return;
        this._running = false;
        window.__sr.stops++;
        if (!this.continuous) window.__sr.captureStops++;
        setTimeout(() => { if (this.onend) this.onend(); }, 0);
      }
      // Test hook: deliver one final transcript, then end the session the way
      // a real one-shot recognition does.
      finish(text) {
        const alt = { transcript: text };
        const result = Object.assign([alt], { isFinal: true, length: 1 });
        if (this.onresult) {
          this.onresult({ resultIndex: 0, results: [result] });
        }
        this.stop();
      }
    }
    window.SpeechRecognition = FakeSR;
    window.webkitSpeechRecognition = FakeSR;
    localStorage.setItem('reclang', 'it');
    localStorage.setItem('source', 'auto');
"""


class TriggeringDetector:
    """Fires the wake word on every chunk, optionally after a delay.

    The delay is what makes the duplicate-trigger test deterministic: the
    browser posts a chunk roughly every 85 ms without waiting for the
    previous answer, so a detector that takes longer than that guarantees
    several chunks are in flight when the first one comes back triggered.
    """

    def __init__(self, delay=0.0):
        self.delay = delay

    def process(self, pcm_bytes):
        if self.delay:
            import time
            time.sleep(self.delay)
        return True

    def reset(self):
        pass


class TriggeringSessions(FakeSessions):
    def __init__(self, trigger_after=2, delay=0.0):
        super().__init__()
        self.trigger_after = trigger_after
        self.delay = delay

    def get_or_create(self, client_id):
        self.chunk_calls += 1
        if self.chunk_calls > self.trigger_after:
            return TriggeringDetector(self.delay)
        return FakeDetector()


def _start_server_wake(page, srv):
    """Boot the page and get to "listening for the wake word, server engine".

    No tap on the mic button: ticking the boxes is enough now that the engine
    choice applies immediately: a tap here would *stop* what they started.
    """
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    _wait_visible(page, "#serverwakerow")
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.check("#wakemode")    # continuous listening on, browser engine
    page.check("#serverwake")  # ...switched to the server engine, live


def test_wake_trigger_lends_the_mic_to_the_capture_and_takes_it_back(
        page_with_fake_mic, web):
    # The input device is exclusive: while the wake stream held it, the
    # command capture heard silence and no command after "hey jarvis" was
    # ever understood. The stream must release the mic (and stop posting
    # chunks) for the length of one capture, then take it back.
    page = page_with_fake_mic
    page.add_init_script(FAKE_SPEECH_RECOGNITION)
    sessions = TriggeringSessions(trigger_after=2)
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    _start_server_wake(page, srv)

    # A one-shot capture opens, not the continuous session Web Speech runs
    # when it is the engine in charge.
    page.wait_for_function("() => window.__sr.captureStarts === 1", timeout=8000)

    # While the capture is open, the wake stream must be silent.
    during = sessions.chunk_calls
    page.wait_for_timeout(600)
    assert sessions.chunk_calls == during, (
        f"wake stream kept posting chunks during the capture "
        f"({during} -> {sessions.chunk_calls}); the mic was never released")

    # The capture ends the way a real one-shot does; the stream takes over.
    page.evaluate("window.__sr.live.finish('pausa')")
    for _ in range(40):
        if sessions.chunk_calls > during:
            break
        page.wait_for_timeout(100)
    assert sessions.chunk_calls > during, (
        "the wake stream never resumed after the command capture")
    # ...and says so: it used to go dark, as if listening had stopped.
    assert page.eval_on_selector("#mic", "el => el.classList.contains('listening')")


def test_duplicate_triggers_do_not_cancel_the_capture(page_with_fake_mic, web):
    # Chunks go out every ~85 ms without waiting, so several are in flight and
    # more than one can come back triggered for the same phrase. The second
    # onTriggered used to call captureCommand() again -> startManual() with
    # the recogniser already running -> rec.stop(): the capture that had just
    # opened was closed a moment later, and nothing was ever heard.
    page = page_with_fake_mic
    page.add_init_script(FAKE_SPEECH_RECOGNITION)
    sessions = TriggeringSessions(trigger_after=0, delay=0.25)
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    _start_server_wake(page, srv)

    page.wait_for_function("() => window.__sr.captureStarts === 1", timeout=8000)
    # Long enough for every chunk that was already in flight to answer.
    page.wait_for_timeout(800)
    assert page.evaluate("window.__sr.captureStops") == 0, (
        "a duplicate trigger stopped the capture that had just opened")
    assert page.evaluate("window.__sr.captureStarts") == 1


def test_switching_engine_while_listening_applies_immediately(
        page_with_fake_mic, web):
    # The engine checkbox used to only write to localStorage: flipping it
    # mid-session changed nothing until wake mode was switched off and on,
    # which read exactly like the choice being ignored.
    page = page_with_fake_mic
    page.add_init_script(FAKE_SPEECH_RECOGNITION)
    sessions = FakeSessions()
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    _start_server_wake(page, srv)

    for _ in range(40):
        if sessions.chunk_calls >= 2:
            break
        page.wait_for_timeout(100)
    assert sessions.chunk_calls >= 2, "no /wakeword/chunk traffic observed"

    page.uncheck("#serverwake")  # back to the browser engine, right now
    for _ in range(40):
        if sessions.stopped:
            break
        page.wait_for_timeout(100)
    assert sessions.stopped, "the server stream kept running after the switch"
    # Web Speech takes over in CONTINUOUS mode: that is its wake mode.
    page.wait_for_function("() => window.__sr.continuous === true", timeout=5000)


def test_wake_panel_shows_the_phrase_and_grammar_of_the_chosen_engine(
        page_with_fake_mic, web):
    # Two engines, two phrases and two ways of speaking: one sentence for the
    # browser one, "phrase, beep, command" for the server one. The panel
    # advertised the free-text word and the single-sentence grammar for both,
    # so testers said "hey jarvis pausa" in one breath at a detector that
    # cannot hear anything after the trigger.
    page = page_with_fake_mic
    page.add_init_script(FAKE_SPEECH_RECOGNITION)
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=FakeSessions())
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    _wait_visible(page, "#serverwakerow")
    page.eval_on_selector("#settings", "el => { el.open = true; }")

    display = "el => getComputedStyle(el).display"
    # Nothing about the engine until continuous listening is even on.
    assert page.eval_on_selector("#wakeopts", display) == "none"
    page.check("#wakemode")
    assert page.eval_on_selector("#wakeopts", display) != "none"

    # Browser engine: the free-text word, and one single sentence.
    assert page.eval_on_selector("#wakehint", display) != "none"
    assert page.eval_on_selector("#wakehint_server", display) == "none"
    assert page.eval_on_selector("#wwlabel", "el => el.textContent") == "vivavoce"
    assert page.eval_on_selector("#wakeword", "el => el.disabled") is False

    # Server engine: the model's own phrase, and the two-step grammar. The
    # free-text field configures nothing here, so it goes away rather than
    # contradicting the hint sitting right next to it.
    page.check("#serverwake")
    assert page.eval_on_selector("#wakehint", display) == "none"
    assert page.eval_on_selector("#wakehint_server", display) != "none"
    assert page.eval_on_selector("#wwlabel_srv", "el => el.textContent") == "Hey Jarvis"
    assert page.eval_on_selector("#wakewordrow", display) == "none"
    assert page.eval_on_selector("#wakeword", "el => el.disabled") is True

    # ...and comes back, with what was typed in it, on the way out.
    page.uncheck("#serverwake")
    assert page.eval_on_selector("#wakehint", display) != "none"
    assert page.eval_on_selector("#wakewordrow", display) != "none"
    assert page.eval_on_selector("#wakeword", "el => el.disabled") is False
    assert page.eval_on_selector("#wakeword", "el => el.value") == "vivavoce"


def test_a_never_started_sessions_end_does_not_erase_the_new_engines_error(
        page, web):
    # The deterministic form of the test above, which was a race for a while.
    #
    # Switching engine calls stopAll() on the browser recogniser and then opens
    # the server one. If the browser session had been *asked* to start but had
    # not yet reported onstart — the normal state a few milliseconds in, and
    # the permanent one wherever Web Speech has no backend — then `active` was
    # still false, so a teardown flag conditioned on it never got set, and the
    # dying session's onend went on to write the idle "tap the mic" over the
    # getUserMedia error the new engine had just reported.
    #
    # A recogniser that never reaches onstart and ends late reproduces that
    # every time, instead of whenever the machine is slow enough.
    page.add_init_script("""
        navigator.mediaDevices.getUserMedia = () =>
            Promise.reject(new DOMException('denied by test', 'NotAllowedError'));
        window.__ends = [];
        class SilentSR {
          constructor() { this.continuous = false; this.lang = ""; }
          start() { /* asked to run; onstart never comes */ }
          stop() {
            // Late, and after the new engine has had its say.
            setTimeout(() => { if (this.onend) this.onend(); }, 200);
          }
        }
        window.SpeechRecognition = SilentSR;
        window.webkitSpeechRecognition = SilentSR;
    """)
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=FakeSessions())
    _start_server_wake(page, srv)

    status = page.locator("#status")
    for _ in range(20):
        if "denied by test" in status.inner_text():
            break
        page.wait_for_timeout(50)
    assert "denied by test" in status.inner_text()

    page.wait_for_timeout(500)  # well past the dying session's onend
    assert "denied by test" in status.inner_text(), (
        f"the torn-down session's onend erased it; status shows "
        f"{status.inner_text()!r}")


# --- switching listening off has to take the capture with it ------------------
#
# The wake stream and the command capture it opens are two different holders of
# the microphone, and only the first one was ever stopped. What the second one
# does when nobody is listening any more is not "nothing": it runs to its own
# timeout and then transcribes and (auto-send being what wake mode implies)
# sends whatever the room happened to be saying, into a UI that went dark
# thirty seconds earlier and said "tap the microphone".

def test_stopping_wake_listening_also_stops_the_open_capture(
        page_with_fake_mic, web):
    page = page_with_fake_mic
    page.add_init_script(FAKE_SPEECH_RECOGNITION)
    sessions = TriggeringSessions(trigger_after=2)
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    _start_server_wake(page, srv)

    page.wait_for_function("() => window.__sr.captureStarts === 1", timeout=8000)
    page.click("#mic")  # "stop listening"

    page.wait_for_function("() => window.__sr.captureStops === 1", timeout=5000)
    assert not page.eval_on_selector(
        "#mic", "el => el.classList.contains('listening')")

    # And what that session still delivers on its way out belongs to nobody:
    # acting on it would answer the room after the panel said it had stopped.
    page.evaluate("window.__sr.live.finish('pausa')")
    page.wait_for_timeout(300)
    assert page.evaluate(
        "[...document.querySelectorAll('#log .bubble')].length") == 0, (
        "a cancelled capture still sent its command")


SLOW_MICROPHONE = """
    // getUserMedia with a real delay in it: the window between asking for the
    // microphone and getting it is where the permission prompt lives, and it
    // is the window every cancel/duplicate guard in mic.js and miccapture.js
    // exists for. Headless Chromium answers instantly, so nothing about that
    // window is reproducible without this.
    const real = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    window.__mic = { calls: 0 };
    navigator.mediaDevices.getUserMedia = (constraints) => {
      window.__mic.calls++;
      return new Promise((resolve, reject) => {
        setTimeout(() => real(constraints).then(resolve, reject), 600);
      });
    };
"""


def test_stopping_while_the_stream_is_opening_really_stops(
        page_with_fake_mic, web):
    # Tearing the session down while startWakeStream() was still pending used
    # to no-op — serverWakeStream is null in that window, so there was nothing
    # to stop — and the pending start then landed anyway: the page went on
    # posting chunks with continuous listening switched off.
    page = page_with_fake_mic
    page.add_init_script(SLOW_MICROPHONE)
    sessions = FakeSessions()
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    _start_server_wake(page, srv)

    page.click("#mic")  # inside the 600 ms opening window
    page.wait_for_timeout(1500)  # well past it

    assert sessions.chunk_calls == 0, (
        f"the cancelled stream started anyway and posted "
        f"{sessions.chunk_calls} chunks")
    assert not page.eval_on_selector(
        "#mic", "el => el.classList.contains('listening')")


class _FakeTranscriber:
    """Enough of the Whisper wrapper for /asr to say the engine is installed;
    the double-tap below never gets as far as transcribing anything."""

    model_name = "tiny"

    def available(self):
        return True

    def transcribe(self, audio, lang):
        return {"text": "pausa", "alternatives": []}


def test_a_second_tap_during_the_permission_prompt_opens_one_stream(
        page_with_fake_mic, web):
    # startLocalRec() guards on `localRec`, which is only assigned AFTER
    # getUserMedia resolves. Two taps while the prompt is up — the normal
    # first-run case on a phone — both passed that guard and opened two
    # streams; the second overwrote the first, whose recorder was then never
    # stopped, whose tracks were never released, and whose recording
    # indicator stayed lit for the life of the page.
    page = page_with_fake_mic
    page.add_init_script(SLOW_MICROPHONE)
    srv = web(license_mgr=_ProLicense(), transcriber=_FakeTranscriber())
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    _wait_visible(page, "#localasrrow")
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.check("#localasr")

    page.click("#mic")
    page.click("#mic")  # still inside the 600 ms window
    page.wait_for_timeout(1200)

    assert page.evaluate("window.__mic.calls") == 1, (
        "the second tap opened a second microphone stream")


def test_switching_engine_while_the_stream_is_opening_still_ends_up_listening(
        page_with_fake_mic, web):
    # A restart asked for while a start is still in flight cannot join it, so
    # it cancels it — and used to start nothing in its place: the box stayed
    # ticked over a page that had quietly stopped listening, and only a fresh
    # tap on the microphone recovered.
    page = page_with_fake_mic
    page.add_init_script(SLOW_MICROPHONE)
    sessions = FakeSessions()
    srv = web(license_mgr=_ProLicense(), wakeword_sessions=sessions)
    _start_server_wake(page, srv)

    # Inside the 600 ms opening window: off and on again.
    page.uncheck("#wakemode")
    page.check("#wakemode")

    for _ in range(60):
        if sessions.chunk_calls > 0:
            break
        page.wait_for_timeout(100)
    assert sessions.chunk_calls > 0, (
        "the restart cancelled the pending start and began nothing")
    assert page.eval_on_selector("#mic", "el => el.classList.contains('listening')")
