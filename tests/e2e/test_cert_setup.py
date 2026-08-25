"""The certificate onboarding, against a real certificate in a real browser.

The friction this removes is the one standing directly in front of the feature
people pay for: the mic needs a secure context, so "your connection is not
private" is the last thing a new user sees before the thing they'd buy. The
pieces to fix it already existed (a local CA, served at /ca.pem) and helped
nobody, because the instructions were collapsed at the bottom of the page,
listed four platforms at once, and offered no way to tell whether any of it
had worked.

So the three claims worth testing are: does the page know which state it is
in, does it show the steps for *this* device, and can it tell the user by
itself that the install succeeded. The last one is not a guess — a browser
refuses to register a service worker on an untrusted certificate — and the
fixtures reproduce both sides of it for real rather than mocking a flag.
"""

STEPS = "#certsteps li"


def state_of(page):
    page.wait_for_function("!!window.vivavoce && window.vivavoce.certState")
    page.wait_for_function("window.vivavoce.certState() !== 'unknown'")
    return page.evaluate("window.vivavoce.certState()")


# -- knowing which state it is in ----------------------------------------------

def test_untrusted_certificate_is_recognised_and_explained(untrusted_page,
                                                           tls_web):
    # The state of every fresh install: HTTPS, warning clicked through, mic
    # still blocked. The panel opens itself — this is the one case where the
    # user cannot be expected to go looking.
    untrusted_page.goto(tls_web())
    assert state_of(untrusted_page) == "untrusted"
    assert untrusted_page.eval_on_selector("#installpanel", "el => el.open")
    assert untrusted_page.query_selector_all(STEPS)


def test_installed_ca_is_recognised_and_says_so(trusted_page, tls_web):
    # The other side of the same signal: with the CA trusted, the service
    # worker registers, and the panel stops asking for anything.
    trusted_page.goto(tls_web())
    assert state_of(trusted_page) == "ok"
    assert trusted_page.query_selector_all(STEPS) == []
    assert trusted_page.is_hidden("#certactions")
    # Which is also the PWA claim: the service worker really did register.
    assert trusted_page.evaluate(
        "navigator.serviceWorker.getRegistration().then(r => !!r)") is True


def test_the_panel_does_not_nag_when_there_is_no_ca_to_install(untrusted_page,
                                                               tls_web):
    # A household using its own certificate has no ca.pem to install, and
    # walking them through installing one would be a wild goose chase.
    untrusted_page.goto(tls_web(ca=False))
    assert state_of(untrusted_page) == "nocert"
    assert untrusted_page.query_selector_all(STEPS) == []


def test_on_the_server_machine_nothing_needs_installing(page, web):
    # Plain HTTP on localhost is a secure context: the mic works, and telling
    # this user to install a certificate would be a lie.
    page.goto(web().url)
    assert state_of(page) == "local"
    assert page.query_selector_all(STEPS) == []
    assert page.eval_on_selector("#installpanel", "el => el.open") is False


# -- steps for THIS device -----------------------------------------------------

def test_steps_are_for_the_platform_in_front_of_you(browser, tls_web):
    # One list per platform, not all four at once. The iPhone case earns its
    # own assertion: its second half (Certificate Trust Settings) is the step
    # everybody misses, and without it nothing works.
    url = tls_web()
    cases = {
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile":
            ("Impostazioni", "Certificato CA"),
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Version/17.0":
            ("Profilo scaricato", "Impostazioni certificati"),
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120":
            ("radice", "attendibili"),
    }
    for ua, expected in cases.items():
        ctx = browser.new_context(ignore_https_errors=True, user_agent=ua)
        page = ctx.new_page()
        page.goto(url)
        state_of(page)
        steps = page.inner_text("#certsteps")
        for phrase in expected:
            assert phrase in steps, f"{ua[:40]}… lost {phrase!r}"
        ctx.close()


def test_the_other_devices_list_is_available_but_folded_away(untrusted_page,
                                                            tls_web):
    # Installing on a phone while reading on a laptop is a real thing people
    # do; the full list stays reachable, just not in the way.
    untrusted_page.goto(tls_web())
    state_of(untrusted_page)
    assert untrusted_page.is_hidden("#certallsteps")
    untrusted_page.click("#certother")
    assert untrusted_page.is_visible("#certallsteps")


# -- checking by itself that it worked -----------------------------------------

def test_verify_reloads_and_reports_the_answer(untrusted_page, tls_web):
    # The button exists because installing the CA changes nothing for a page
    # already loaded over that connection: the answer only arrives on reload.
    untrusted_page.goto(tls_web())
    state_of(untrusted_page)
    untrusted_page.click("#certverify")
    untrusted_page.wait_for_function("!!window.vivavoce")
    # Still untrusted (nothing was actually installed), and the panel is open
    # on the answer rather than leaving the user to go find it again.
    assert state_of(untrusted_page) == "untrusted"
    assert untrusted_page.eval_on_selector("#installpanel", "el => el.open")


def test_the_verdict_survives_a_language_switch(untrusted_page, tls_web):
    # applyUI() re-renders every panel from the markup snapshot; this one has
    # no snapshot to go back to, so it has to be re-rendered from live state.
    untrusted_page.goto(tls_web())
    state_of(untrusted_page)
    untrusted_page.select_option("#reclang", "en")
    assert "does not trust" in untrusted_page.inner_text("#certstate")
    assert untrusted_page.query_selector_all(STEPS)
    untrusted_page.select_option("#reclang", "it")
    assert "non si fida" in untrusted_page.inner_text("#certstate")


def test_plain_http_from_another_device_says_so_and_offers_no_certificate(
        page, http_elsewhere_web):
    # No certificate installed on the *phone* can rescue a server that speaks
    # plain HTTP, so offering to install one would send the user down a road
    # with nothing at the end of it. The server has to serve TLS first.
    page.goto(http_elsewhere_web)
    assert state_of(page) == "http"
    assert page.query_selector_all(STEPS) == []
    assert page.eval_on_selector("#installpanel", "el => el.open") is False
    # And the free half of the product is untouched by any of this.
    page.fill("#text", "pausa")
    page.click("#send")
    reply = page.wait_for_selector("#log .bubble.sys:not(.pending)")
    assert reply.inner_text() == "In pausa."
