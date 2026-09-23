"""The public demo page, in a real browser, running the real Router in Pyodide.

``tests/test_demo.py`` holds the demo's Python to account under CPython; this
file holds the *page*: that Pyodide boots, that the core arrives from where the
page says it lives, and that a typed phrase and a tapped number come back as a
reply and a record on the pretend hi-fi.

Nothing leaves the machine. The page is opened at its real address and every
request is answered by ``page.route`` from disk:

* ``lucabon.github.io/vivavoce/`` — from ``docs/``, which is what Pages serves;
* ``cdn.jsdelivr.net/pyodide/…`` — from ``.cache/pyodide/<version>/``, which
  ``tools/fetch_pyodide.py`` fills once, like ``playwright install``;
* ``cdn.jsdelivr.net/gh/LucaBon/vivavoce@<tag>/…`` — from this working tree,
  so the page runs the code under test and not whatever the tag holds.

Anything else is aborted and fails the test: a page that quietly reached for a
third host would work here and break the day that host changes.
"""

import json
import mimetypes
import os
import sys

import pytest

from .conftest import _skip_or_fail

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fetch_pyodide  # noqa: E402

SITE = "https://lucabon.github.io/vivavoce/"
PYODIDE = f"https://cdn.jsdelivr.net/pyodide/v{fetch_pyodide.version()}/full/"
with open(os.path.join(ROOT, "docs", "demo", "core-files.json"), encoding="utf-8") as _f:
    CORE = f"https://cdn.jsdelivr.net/gh/LucaBon/vivavoce@{json.load(_f)['ref']}/"
BOOT_TIMEOUT = 60_000


def _serve_from(base_dir):
    def handler(route, prefix):
        rel = route.request.url.split("?", 1)[0][len(prefix):] or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        path = os.path.normpath(os.path.join(base_dir, rel))
        if not path.startswith(base_dir + os.sep) or not os.path.isfile(path):
            return route.fulfill(status=404, body="not found")
        ctype = ("application/wasm" if path.endswith(".wasm") else
                 mimetypes.guess_type(path)[0] or "application/octet-stream")
        with open(path, "rb") as f:
            route.fulfill(status=200, body=f.read(), content_type=ctype,
                          headers={"Access-Control-Allow-Origin": "*"})
    return handler


@pytest.fixture
def demo_page(page):
    cache = fetch_pyodide.cache_dir()
    missing = [f for f in fetch_pyodide.FILES
               if not os.path.isfile(os.path.join(cache, f))]
    if missing:
        _skip_or_fail(f"Pyodide not cached ({', '.join(missing)} missing): "
                      "uv run python tools/fetch_pyodide.py")
    escaped = []
    served = {SITE: _serve_from(os.path.join(ROOT, "docs")),
              PYODIDE: _serve_from(cache),
              CORE: _serve_from(ROOT)}

    def route(route):
        url = route.request.url
        for prefix, handler in served.items():
            if url.startswith(prefix):
                return handler(route, prefix)
        escaped.append(url)
        return route.abort()

    page.route("**/*", route)
    yield page
    assert escaped == [], f"the page reached outside its three origins: {escaped}"


def boot(page):
    page.goto(SITE + "demo/")
    page.wait_for_selector("#status[data-state=ready]", timeout=BOOT_TIMEOUT)
    page.select_option("#lang", "it")


def say(page, text):
    replies = page.locator("#log .app").count()
    page.fill("#say", text)
    page.press("#say", "Enter")
    page.wait_for_function(
        f"document.querySelectorAll('#log .app').length > {replies}")
    return page.locator("#log .app").last.inner_text()


def test_a_phrase_a_list_and_a_tap(demo_page):
    page = demo_page
    boot(page)

    assert "Riproduco Time di Pink Floyd" in say(page, "metti Time dei Pink Floyd")
    assert "Time" in page.inner_text("#now")
    assert "Pink Floyd" in page.inner_text("#now")

    # the promise the page exists for: a song it has not got starts nothing
    reply = say(page, "metti Wish You Were Here")
    assert "Wish You Were Here" in reply
    assert "Pink Floyd" in page.inner_text("#now")
    assert page.locator("#told [data-empty]").count() == 1

    say(page, "quali sono i brani di Pink Floyd")
    buttons = page.locator("#log .choice")
    assert buttons.count() == 3
    before = page.locator("#log .app").count()
    buttons.nth(1).click()
    page.wait_for_function(
        f"document.querySelectorAll('#log .app').length > {before}")
    assert "Riproduco Money" in page.locator("#log .app").last.inner_text()
    assert "Money" in page.inner_text("#now")


def test_a_suggestion_is_a_phrase_in_the_chosen_language(demo_page):
    page = demo_page
    boot(page)
    page.select_option("#lang", "en")
    chip = page.locator(".chip").first
    assert chip.inner_text() == "play Time by Hans Zimmer"
    chip.click()
    page.wait_for_function("document.querySelectorAll('#log .app').length > 0")
    assert "Playing Time by Hans Zimmer" in page.locator("#log .app").last.inner_text()


def test_the_first_search_hit_is_shown_beside_the_right_record(demo_page):
    """The point of the page: the typical assistant's column plays Pink
    Floyd's «Time», is marked wrong, and the hi-fi plays Zimmer's."""
    page = demo_page
    boot(page)
    say(page, "metti Time di Hans Zimmer")
    wrong = page.locator("#log .exchange").last.locator(".col.typical.wrong")
    assert wrong.count() == 1
    assert "Time — Pink Floyd" in wrong.inner_text()
    assert "Hans Zimmer" in page.inner_text("#now")
    assert page.inner_text("#avoided") == "1"

    say(page, "metti Time dei Pink Floyd")
    last = page.locator("#log .exchange").last
    assert last.locator(".col.typical").count() == 0
    assert last.locator(".agree").count() == 1
    assert page.inner_text("#avoided") == "1"


def test_the_reply_is_said_aloud_and_can_be_silenced(demo_page):
    page = demo_page
    # Headless Chromium has no voices; what matters is what the page asks for.
    page.add_init_script("""
        window.__spoken = [];
        window.speechSynthesis.speak = (u) => window.__spoken.push([u.text, u.lang]);
        window.speechSynthesis.cancel = () => {};
    """)
    boot(page)
    say(page, "metti Wish You Were Here")
    spoken = page.evaluate("window.__spoken")
    assert spoken[-1][1] == "it-IT"
    assert "Wish You Were Here" in spoken[-1][0]

    page.click("#voice")
    assert page.get_attribute("#voice", "aria-pressed") == "false"
    say(page, "pausa")
    assert page.evaluate("window.__spoken.length") == len(spoken)


def test_an_album_shows_what_comes_next(demo_page):
    page = demo_page
    boot(page)
    say(page, "metti l'album The Dark Side of the Moon")
    assert page.locator("#queue li").all_inner_texts() == [
        "Money — Pink Floyd", "Breathe — Pink Floyd"]


def test_a_cdn_that_does_not_answer_is_said_on_the_page(page):
    """No Pyodide, no demo — but a sentence, not a spinner forever."""
    docs = _serve_from(os.path.join(ROOT, "docs"))
    page.route("**/*", lambda r: docs(r, SITE) if r.request.url.startswith(SITE)
               else r.abort())
    page.goto(SITE + "demo/")
    page.wait_for_selector("#status[data-state=error]", timeout=BOOT_TIMEOUT)
    assert page.locator("#say").is_disabled()


@pytest.mark.parametrize("trick", [
    "%5C%5Cevil.example/", "/%5Cevil.example/", "%20//evil.example/",
    "/%09/evil.example/", "https://evil.example/", "//evil.example/",
])
def test_a_link_cannot_point_the_page_at_another_servers_python(demo_page, trick):
    """``?core=`` is for trying a working tree on this site. Every spelling
    that a browser resolves to another host must be ignored — the page then
    loads its own engine, and ``demo_page`` fails if anything reached out."""
    page = demo_page
    page.goto(SITE + "demo/?core=" + trick)
    page.wait_for_selector("#status[data-state=ready]", timeout=BOOT_TIMEOUT)
