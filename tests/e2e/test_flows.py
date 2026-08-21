"""The critical user flows, in a real browser.

Five journeys the backend suite cannot see (they live in the page's JS):
loading the page at all, the text-command round trip, tapping a "did you
mean" choice, activating a Pro license from settings, the now-playing panel,
and settings persistence across a reload. The LMS is the same fake transport
as everywhere else; the license server is an injected ``http_post``.
"""

import licensing

YES_ALBUMS = {"albums_loop": [{"id": 345, "album": "90125"},
                              {"id": 9, "album": "Fragile"}]}


def test_page_loads_with_all_modules(page, web):
    # The page dies as a unit if any ES module 404s or throws at import time;
    # the `page` fixture additionally asserts no uncaught JS errors.
    page.goto(web().url)
    page.wait_for_function("!!window.vivavoce")
    assert page.is_visible("#mic")
    assert page.is_visible("#text")
    # The server-injected services reached the source selector.
    values = page.eval_on_selector_all(
        "#source option", "opts => opts.map(o => o.value)")
    assert values == ["auto", "local", "tidal"]


def test_text_command_round_trip(page, web, transport):
    page.goto(web().url)
    page.fill("#text", "pausa")
    page.click("#send")
    reply = page.wait_for_selector("#log .bubble.sys:not(.pending)")
    assert reply.inner_text() == "In pausa."
    # The command really reached the (fake) LMS.
    assert ["pause", "1"] in transport.commands()


def test_did_you_mean_tap_plays_the_pick(page, web, transport):
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = YES_ALBUMS
    page.goto(web().url)
    page.fill("#text", "quali album ho di Yes")
    page.click("#send")
    # The numbered list renders as tappable buttons under the reply.
    page.click("#log .choices .choice:has-text('2 · Fragile')")
    page.wait_for_function(
        "document.querySelectorAll('#log .bubble.sys:not(.pending)').length >= 2")
    assert ["playlistcontrol", "cmd:load", "album_id:9"] in transport.commands()


def test_license_activation_unlocks_the_mic(page, web, tmp_path):
    # A real LicenseManager on a temp dir; only the HTTP transport is fake.
    mgr = licensing.LicenseManager(
        str(tmp_path),
        http_post=lambda url, fields: (200, {"activated": True,
                                             "instance": {"id": "i-1"}}))
    page.goto(web(license_mgr=mgr).url)
    # Free tier: the knob is visibly off.
    page.wait_for_selector("#mic.locked")
    # First-ever visit auto-opens settings; force the state instead of
    # toggling the summary (a click would close it again).
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.fill("#prokey", "TEST-KEY-1234-ABCD")
    page.click("#proact")
    # Activation flips the served state and the page applies it: mic unlocked,
    # status line shows the masked key.
    page.wait_for_selector("#mic:not(.locked)")
    assert "****ABCD" in page.inner_text("#prostatus")
    assert mgr.is_pro()


def test_nowplaying_panel_renders_the_track(page, web, transport):
    transport.responses["status"] = {
        "mode": "play", "time": 42.5,
        "playlist_loop": [{"title": "Time", "artist": "Pink Floyd",
                           "album": "The Dark Side of the Moon",
                           "coverid": "ab12cd", "duration": 421}],
    }
    page.goto(web().url)
    page.wait_for_selector("#np:not([hidden])")
    assert page.inner_text("#nptitle") == "Time"
    assert "Pink Floyd" in page.inner_text("#npsub")
    # The artwork goes through the server-side proxy, not the LMS directly.
    assert page.get_attribute("#npart", "src").startswith("/artwork?")


def test_settings_persist_across_reload(page, web):
    url = web().url
    page.goto(url)
    page.eval_on_selector("#settings", "el => { el.open = true; }")
    page.select_option("#source", "local")
    page.select_option("#reclang", "en")
    # The language switch re-renders the chrome immediately...
    page.wait_for_function("document.documentElement.lang === 'en'")
    assert "local voice control" in page.inner_text("h1")
    # ...and both choices survive a reload (localStorage).
    page.reload()
    page.wait_for_function("document.documentElement.lang === 'en'")
    assert page.input_value("#source") == "local"
    assert page.input_value("#reclang") == "en"
