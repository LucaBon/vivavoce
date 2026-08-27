"""What the installed app keeps, in a real service worker.

The registration itself is covered by ``test_cert_setup.py`` — a browser only
accepts a service worker over a *trusted* certificate, which is why these
tests need the same CA-installed fixture. What is covered here is the rule the
network-first branch of ``sw.js`` lives by: the cache is the app's offline
copy of itself, so only a response that IS the app may go into it.

An error is a fact about right now, not a version of the app to keep. Caching
one puts a 403/404/500 body under ``"/"`` or under a module's key, and the
installed app then opens offline on the error page — or on a module whose body
is HTML served as ``text/javascript``, which is a blank app that no amount of
reloading offline can fix.
"""


def _boot_with_service_worker(page, url):
    page.goto(url)
    page.wait_for_function("!!window.vivavoce")
    # skipWaiting + clients.claim, so this page ends up controlled without a
    # reload; until it is, its fetches never reach the worker at all.
    page.wait_for_function("() => navigator.serviceWorker.controller !== null",
                           timeout=15000)


def _cached_status(page, path):
    """The status of what the cache holds for ``path``, or None."""
    return page.evaluate(
        "p => caches.match(p).then(r => (r ? r.status : null))", path)


def test_a_good_asset_is_cached_for_offline(trusted_page, tls_web):
    # The control: the network-first branch really does keep what it fetches,
    # or the test below would pass with caching switched off entirely.
    page = trusted_page
    _boot_with_service_worker(page, tls_web())

    page.evaluate("fetch('/static/js/mic.js').then(r => r.text())")
    page.wait_for_function(
        "() => caches.match('/static/js/mic.js').then(r => !!r)", timeout=5000)
    assert _cached_status(page, "/static/js/mic.js") == 200


def test_an_error_is_not_cached_over_the_shell(trusted_page, tls_web):
    page = trusted_page
    _boot_with_service_worker(page, tls_web())

    status = page.evaluate(
        "fetch('/static/js/no-such-module.js').then(r => r.status)")
    assert status == 404
    page.wait_for_timeout(500)  # well past the put this used to do
    assert _cached_status(page, "/static/js/no-such-module.js") is None, (
        "the service worker stored an error response as the app's own copy")
