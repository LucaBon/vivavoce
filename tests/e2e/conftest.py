"""Browser-level fixtures for the end-to-end suite.

The rest of the suite drives the HTTP handler; these drive the real page in a
real (headless) browser, because the frontend is where module wiring, fetch
contracts and rendering can break with every backend test still green.

Kept cheap and honest:

* the backend is the same ``live_server`` + ``FakeTransport`` stack the HTTP
  tests use — no network, no LMS;
* Playwright is already a dev dependency (the screenshot harness uses it);
  the browser binary may still be missing (fresh checkout, CI matrix jobs
  that never installed it), so the whole directory skips cleanly then —
  ``uv run playwright install chromium`` enables it;
* every page records uncaught JS errors; ``page`` asserts none at teardown,
  so a broken module import fails loudly in any test that touches the page.
"""

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is not installed (dev group)")


@pytest.fixture(scope="session")
def _playwright():
    # One Playwright instance for the whole session: the sync API manages
    # its own event loop internally, and a second concurrent
    # `sync_playwright()` context (e.g. one per browser fixture) raises
    # "already in an asyncio loop" the moment both are live at once. Every
    # browser launches from this single shared instance instead.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(_playwright):
    from playwright.sync_api import Error
    try:
        browser = _playwright.chromium.launch()
    except Error as exc:
        pytest.skip(f"chromium not available: {exc}")
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def browser_with_fake_mic(_playwright):
    """A separate Chromium instance with a synthetic microphone (silence/a
    simple tone, never a real spoken phrase) — only for the one test that
    needs getUserMedia to actually resolve without a real device or an OS
    permission prompt. Kept apart from ``browser`` so the fake-media flags
    never leak into ordinary page tests."""
    from playwright.sync_api import Error
    try:
        browser = _playwright.chromium.launch(args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ])
    except Error as exc:
        pytest.skip(f"chromium not available: {exc}")
    yield browser
    browser.close()


@pytest.fixture
def page(browser):
    """A fresh browser context per test (own localStorage), with uncaught
    page errors collected and asserted empty at teardown."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    yield page
    ctx.close()
    assert errors == [], f"uncaught JS errors on the page: {errors}"


@pytest.fixture
def page_with_fake_mic(browser_with_fake_mic):
    """Like ``page``, but on the fake-microphone browser (see
    ``browser_with_fake_mic``)."""
    ctx = browser_with_fake_mic.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    yield page
    ctx.close()
    assert errors == [], f"uncaught JS errors on the page: {errors}"


class _FakeArtworkFetch:
    """Keeps /artwork off the network (a 1x1 PNG would be overkill)."""

    def __call__(self, url, timeout=5.0):
        return "image/png", b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def web(live_server, transport):
    """Factory: a live server whose /artwork never leaves the process, plus
    a quiet LMS (mode stop) so the page boots with the lamp green."""
    transport.responses.setdefault("status", {"mode": "stop"})

    def start(**kwargs):
        kwargs.setdefault("artwork_fetch", _FakeArtworkFetch())
        return live_server(**kwargs)

    return start


# -- TLS, for the certificate onboarding ---------------------------------------
#
# The certificate panel only says anything interesting over HTTPS, and the two
# states that matter cannot be faked with a flag: "the user clicked through the
# warning" and "the CA is installed" differ precisely in whether the browser
# will register a service worker, which is the signal certsetup.js reads.
#
# Both are reproduced for real:
#
# * untrusted — an ordinary browser with ``ignore_https_errors=True``. The page
#   loads (exactly what clicking through the interstitial does) and Chrome
#   still refuses the service worker with a SecurityError;
# * trusted — a browser launched with ``--ignore-certificate-errors``, which
#   makes it treat the connection as genuinely secure, the way an installed CA
#   does. There the same registration succeeds.
#
# The certificate is the real one ``tools/make_cert.py`` writes, generated once
# per session into a temp dir; nothing touches the network.

@pytest.fixture(scope="session")
def local_ca(tmp_path_factory):
    """``(dir, cert, key)`` from the real cert tool — ca.pem included."""
    import subprocess
    import sys
    out = tmp_path_factory.mktemp("tls")
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(out)],
        capture_output=True, text=True)
    if proc.returncode != 0:  # cryptography missing: nothing to test here
        pytest.skip(f"make_cert failed: {proc.stderr[-300:]}")
    return out, str(out / "cert.pem"), str(out / "key.pem")


@pytest.fixture(scope="session")
def browser_trusting_certs(_playwright):
    """A browser that trusts the local CA, i.e. one where the user completed
    the install the panel is walking them through."""
    from playwright.sync_api import Error
    try:
        browser = _playwright.chromium.launch(
            args=["--ignore-certificate-errors"])
    except Error as exc:
        pytest.skip(f"chromium not available: {exc}")
    yield browser
    browser.close()


@pytest.fixture
def tls_web(lms, local_ca, transport):
    """Factory: the real handler over real TLS. ``ca=False`` serves the same
    certificate without offering a ca.pem, which is what a household using its
    own certificate looks like."""
    import threading
    from http.server import ThreadingHTTPServer

    import server as srv
    import tls
    from conftest import DEFAULT_MATERIAL_URL

    transport.responses.setdefault("status", {"mode": "stop"})
    _dir, cert, key = local_ca
    servers = []

    def start(ca=True, **kwargs):
        kwargs.setdefault("artwork_fetch", _FakeArtworkFetch())
        handler = srv.make_handler(
            lms, DEFAULT_MATERIAL_URL, ["tidal"], "tidal",
            ca_path=(tls.find_ca(cert) if ca else None), **kwargs)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        tls.wrap_server(httpd, cert, key)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"https://127.0.0.1:{httpd.server_address[1]}"

    yield start
    for httpd in servers:
        httpd.shutdown()


def _tls_page(browser, **ctx_kwargs):
    """A page that accepts the certificate the way a user who clicked through
    the warning does, with uncaught JS errors collected."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              ignore_https_errors=True, **ctx_kwargs)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return ctx, page, errors


@pytest.fixture
def http_elsewhere_web(lms, transport):
    """The handler over plain HTTP on 127.0.0.2 — still loopback (the whole
    127/8 block is), so no network is touched, but the page does not see
    "localhost" and lands in the same state a phone would: HTTP from another
    device, where no certificate installed on the phone can help."""
    import threading
    from http.server import ThreadingHTTPServer

    import server as srv
    from conftest import DEFAULT_MATERIAL_URL

    transport.responses.setdefault("status", {"mode": "stop"})
    handler = srv.make_handler(lms, DEFAULT_MATERIAL_URL, ["tidal"], "tidal",
                               artwork_fetch=_FakeArtworkFetch())
    try:
        httpd = ThreadingHTTPServer(("127.0.0.2", 0), handler)
    except OSError as exc:  # not every platform routes the whole 127/8
        pytest.skip(f"127.0.0.2 not bindable here: {exc}")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.2:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def untrusted_page(browser):
    """The state every fresh install is in: HTTPS, warning clicked through,
    certificate still not trusted."""
    ctx, page, errors = _tls_page(browser)
    yield page
    ctx.close()
    assert errors == [], f"uncaught JS errors on the page: {errors}"


@pytest.fixture
def trusted_page(browser_trusting_certs):
    """After the user has installed the CA."""
    ctx, page, errors = _tls_page(browser_trusting_certs)
    yield page
    ctx.close()
    assert errors == [], f"uncaught JS errors on the page: {errors}"
