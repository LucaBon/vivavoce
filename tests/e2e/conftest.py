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
