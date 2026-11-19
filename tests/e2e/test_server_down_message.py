"""Who is not answering decides what the status line says.

``/nowplaying`` failing outright means Vivavoce itself did not answer — the
server is stopped, or the page was opened at an address it no longer serves
(``https://`` from the installed app's cache while the server now runs on
``http://``). The page used to say "can't reach the music server (LMS)" for
that too, and sent people to check a hi-fi that was fine. Only a reply that
says ``mode: unknown`` — Vivavoce up, the LMS behind it not — is the LMS.
"""


def _open(page, srv):
    page.add_init_script("localStorage.setItem('reclang', 'it');")
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")


def _poll_now(page):
    page.evaluate("import('/static/js/nowplaying.js')"
                  ".then(m => m.refreshNowPlaying())")


def test_no_answer_from_the_server_does_not_blame_the_lms(page, web):
    srv = web()
    _open(page, srv)
    page.route("**/nowplaying*", lambda route: route.abort())
    _poll_now(page)
    page.wait_for_function(
        "document.getElementById('status').innerText.includes('Vivavoce')",
        timeout=5000)
    status = page.inner_text("#status")
    assert "Non raggiungo Vivavoce" in status, status
    assert "LMS" not in status, status


def test_an_unknown_mode_still_names_the_lms(page, web):
    srv = web()
    _open(page, srv)
    page.route("**/nowplaying*", lambda route: route.fulfill(
        status=200, content_type="application/json", body='{"mode": "unknown"}'))
    _poll_now(page)
    page.wait_for_function(
        "document.getElementById('status').innerText.includes('LMS')",
        timeout=5000)
    assert "server musicale (LMS)" in page.inner_text("#status")
