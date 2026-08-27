"""The first-install Pro window, in a real browser.

The server-side half (``tests/test_licensing.py``) proves the window opens
once, closes on its date and gates the two endpoints that cost CPU. What it
cannot see is the half the money depends on: whether the page tells the truth
about a Pro nobody paid for, and whether the upgrade ask arrives at the moment
it means something instead of buried in a settings panel.

Every test drives a real ``LicenseManager`` over a temp dir with its clock
moved, so "day 3" and "day 15" are the real thing rather than a mocked flag.
"""

import licensing

DAY = 24 * 3600
# After licensing.BUILD_EPOCH: the manager refuses to open a window while the
# clock reads earlier than this code existed (the pre-NTP Pi case, covered in
# tests/test_licensing.py), so a 1970-ish fixture time would leave every test
# here staring at a page with no window at all.
OPENED = 1_800_000_000  # 2027-01-15T08:00:00Z


def trial_at(tmp_path, day, key=None):
    """A manager whose window opened on day 1 and whose clock now reads ``day``
    (1-based, matching what the page is told). ``key`` activates a license
    first, for the "somebody actually paid" cases."""
    mgr = licensing.LicenseManager(
        str(tmp_path), now=lambda: OPENED,
        http_post=lambda url, fields: (200, {"activated": True,
                                             "instance": {"id": "i-1"}}))
    mgr.start_trial()
    if key:
        mgr.activate(key)
    mgr.now = lambda: OPENED + (day - 1) * DAY
    return mgr


def command(page, text="pausa"):
    """Type a command and wait for the server's reply bubble."""
    before = page.eval_on_selector_all(
        "#log .bubble.sys:not(.pending)", "els => els.length")
    page.fill("#text", text)
    page.click("#send")
    page.wait_for_function(
        "n => document.querySelectorAll('#log .bubble.sys:not(.pending)')"
        ".length > n", arg=before)


# -- what the panel says -------------------------------------------------------

def test_window_unlocks_the_mic_with_no_key_at_all(page, web, tmp_path):
    # The whole point of the window: the magic is available on day one,
    # without anyone having typed a license key.
    page.goto(web(license_mgr=trial_at(tmp_path, day=1)).url)
    page.wait_for_selector("#mic:not(.locked)")
    assert page.eval_on_selector("#wakemode", "el => el.disabled") is False


def test_panel_says_trial_not_license_active(page, web, tmp_path):
    # The lie worth avoiding: "Pro active — license ****" during a window
    # nobody paid for is discovered on day 15, the worst day to discover it.
    page.goto(web(license_mgr=trial_at(tmp_path, day=1)).url)
    page.wait_for_selector("#mic:not(.locked)")
    status = page.inner_text("#prostatus")
    assert "14" in status
    assert "****" not in status
    # And it still offers to sell, which the paid state does not.
    assert page.is_visible("#probuy")
    assert page.is_visible("#prorow")


def test_last_days_are_emphasised(page, web, tmp_path):
    page.goto(web(license_mgr=trial_at(tmp_path, day=12)).url)
    page.wait_for_selector("#prostatus.warn")
    assert "3" in page.inner_text("#prostatus")


def test_expired_window_locks_the_mic_and_explains_itself(page, web, tmp_path):
    page.goto(web(license_mgr=trial_at(tmp_path, day=15)).url)
    page.wait_for_selector("#mic.locked")
    # NOT enough on its own: applyPro() runs at boot with no server data yet
    # and locks the mic then, so that selector is already true before
    # /license has answered — the panel is still showing the generic Pro
    # pitch. Waiting for the copy itself is the wait for the answer, and it
    # still fails (by timing out) if the answer never says "expired".
    page.wait_for_function(
        "() => /prova|trial/i.test("
        "document.getElementById('prostatus').textContent)", timeout=5000)
    status = page.inner_text("#prostatus").lower()
    assert "prova" in status or "trial" in status
    # "Never brick": typed commands are untouched by the expiry.
    command(page)
    assert page.inner_text("#log .bubble.sys:not(.pending)") == "In pausa."


def test_a_paid_licence_is_not_shown_as_a_trial(page, web, tmp_path):
    page.goto(web(license_mgr=trial_at(tmp_path, day=20, key="K-1234-ABCD")).url)
    page.wait_for_selector("#mic:not(.locked)")
    assert "****ABCD" in page.inner_text("#prostatus")
    assert page.is_hidden("#probuy")


# -- the in-flow ask -----------------------------------------------------------

def test_typed_command_prompts_to_try_the_mic(page, web, tmp_path):
    # The ask, moved out of the settings panel and into the one moment it is
    # concrete: just after something the user typed and could have said.
    page.goto(web(license_mgr=trial_at(tmp_path, day=3)).url)
    page.wait_for_selector("#mic:not(.locked)")
    command(page)
    prompt = page.wait_for_selector("#log .bubble.upsell")
    assert "🎙" in prompt.inner_text() or "👆" in prompt.inner_text()


def test_the_prompt_does_not_come_before_the_third_day(page, web, tmp_path):
    page.goto(web(license_mgr=trial_at(tmp_path, day=2)).url)
    page.wait_for_selector("#mic:not(.locked)")
    command(page)
    assert page.query_selector("#log .bubble.upsell") is None


def test_the_prompt_comes_at_most_once_per_session(page, web, tmp_path):
    page.goto(web(license_mgr=trial_at(tmp_path, day=5)).url)
    page.wait_for_selector("#mic:not(.locked)")
    command(page)
    page.wait_for_selector("#log .bubble.upsell")
    command(page, "avanti")
    command(page, "pausa")
    assert len(page.query_selector_all("#log .bubble.upsell")) == 1


def test_a_paying_user_is_never_prompted(page, web, tmp_path):
    page.goto(web(license_mgr=trial_at(tmp_path, day=5, key="K-1234-ABCD")).url)
    page.wait_for_selector("#mic:not(.locked)")
    command(page)
    assert page.query_selector("#log .bubble.upsell") is None


def test_after_expiry_the_prompt_opens_the_pro_panel(page, web, tmp_path):
    # Once the window has closed the same moment becomes a real ask, and it
    # has to lead somewhere: one tap to the panel that sells the licence.
    page.goto(web(license_mgr=trial_at(tmp_path, day=20)).url)
    page.wait_for_selector("#mic.locked")
    page.eval_on_selector("#settings", "el => { el.open = false; }")
    command(page)
    page.wait_for_selector("#log .bubble.upsell")
    page.click("#log .choices .choice")
    assert page.eval_on_selector("#settings", "el => el.open") is True


def test_a_failed_command_is_not_an_upgrade_pitch(page, web, tmp_path):
    # Stapling the ask to a failure reads as "pay us and maybe it will
    # understand you", which is not the offer being made.
    page.goto(web(license_mgr=trial_at(tmp_path, day=5)).url)
    page.wait_for_selector("#mic:not(.locked)")
    command(page, "sgrunf blarg zorp")
    assert page.query_selector("#log .bubble.upsell") is None


def test_expiry_puts_the_whole_wake_block_away(page, web, tmp_path):
    # applyPro() unticks wake mode and hid #wakehint — which the index.html
    # split left as just the inner paragraph. The container it moved to is
    # #wakeopts, so everything that configures continuous listening (engine
    # choice, keyword field) stayed on screen under a disabled checkbox.
    page.add_init_script("localStorage.setItem('wakemode', '1');")
    page.goto(web(license_mgr=trial_at(tmp_path, day=15)).url)
    page.wait_for_function(
        "() => /prova|trial/i.test("
        "document.getElementById('prostatus').textContent)", timeout=5000)
    page.eval_on_selector("#settings", "el => { el.open = true; }")

    assert page.eval_on_selector("#wakemode", "el => el.checked") is False
    assert page.eval_on_selector(
        "#wakeopts", "el => getComputedStyle(el).display") == "none", (
        "the continuous-listening block outlived the trial that unlocked it")


class _WakeSessions:
    """Enough of pro.wakeword.ServerWakeWordSessions for /wakeword to say the
    server-side engine exists, so the panel can be in its state."""

    model = "hey_jarvis"

    def available(self):
        return True


def test_expiry_hands_the_wake_panel_back_to_the_browser_engine(
        page, web, tmp_path):
    # applyPro() unticks #serverwake directly, without the reconciler that
    # owns what the panel says about the engine — so the panel kept the
    # server engine's two-step hint and its "the phrase is fixed" hidden
    # keyword field, while the browser engine was what would actually run.
    page.add_init_script("localStorage.setItem('wakemode', '1');"
                         "localStorage.setItem('serverwake', '1');")
    srv = web(license_mgr=trial_at(tmp_path, day=15),
              wakeword_sessions=_WakeSessions())
    page.goto(srv.url)
    page.wait_for_function(
        "() => /prova|trial/i.test("
        "document.getElementById('prostatus').textContent)", timeout=5000)
    page.eval_on_selector("#settings", "el => { el.open = true; }")

    # The panel as a Pro household left it: server engine selected.
    page.evaluate("document.getElementById('serverwake').checked = true")
    page.evaluate("window.vivavoce.refreshServerWake()")
    page.wait_for_function(
        "() => document.getElementById('wakewordrow').style.display === 'none'",
        timeout=5000)

    page.evaluate("window.vivavoce.refreshLicense()")
    page.wait_for_function(
        "() => !document.getElementById('serverwake').checked", timeout=5000)
    assert page.eval_on_selector(
        "#wakewordrow", "el => el.style.display") != "none", (
        "the keyword field stayed hidden for an engine no longer selected")
    assert page.eval_on_selector(
        "#wakehint_server", "el => el.style.display") == "none"
