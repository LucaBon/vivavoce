"""Material Skin inside the page, in a real browser.

The whole point of the reverse proxy is a thing only a browser can show: that
opening someone else's application does not take the microphone off the
screen. So this drives the real page — the click, the frame, the knob that has
to still be there, the Back button that has to mean "close this" — against the
fake upstream the e2e fixtures put behind the proxy.

kid-safe is here too, because "hide the door on a locked device" is a claim
about the rendered page and nothing below the browser can check it.
"""

from conftest import FakeLicense
from pro.kidsafe import KidSafe


def _locked_kidsafe(tmp_path):
    """A real KidSafe, switched on, with this device locked."""
    ks = KidSafe(str(tmp_path), FakeLicense(pro=True))
    ks.enable("123456", "setup")
    ks.lock("setup")
    return ks


def test_the_link_opens_material_in_the_page(page, web):
    page.goto(web().url)
    page.wait_for_function("!!window.vivavoce")
    page.click("#material")
    frame = page.wait_for_selector("#browseframe")
    assert frame.is_visible()
    # The frame really loaded through the proxy, i.e. from this origin.
    assert page.frame_locator("#browseframe").locator("h1").inner_text() \
        == "Material"


def test_the_microphone_stays_on_screen_while_browsing(page, web):
    page.goto(web().url)
    page.wait_for_function("!!window.vivavoce")
    page.click("#material")
    page.wait_for_selector("#browse:not([hidden])")
    # The reason the panel exists at all: the product is still one tap away.
    assert page.is_visible("#mic")
    assert page.is_visible("#text")
    assert page.is_visible("#ainotice")


def test_closing_returns_to_the_commands(page, web):
    page.goto(web().url)
    page.wait_for_function("!!window.vivavoce")
    page.click("#material")
    page.wait_for_selector("#browse:not([hidden])")
    page.click("#browseclose")
    page.wait_for_selector("#browse", state="hidden")
    assert page.is_visible("#empty")   # the suggestions, back where they were


def test_the_close_button_still_closes_after_browsing_inside_the_frame(page, web):
    # The panel is closed directly, not with history.back(): navigating inside
    # the iframe adds entries to the JOINT session history, so a back() here
    # would step around inside Material and the button would look dead.
    page.goto(web().url)
    page.wait_for_function("!!window.vivavoce")
    page.click("#material")
    page.wait_for_selector("#browse:not([hidden])")
    frame = page.frame_locator("#browseframe")
    frame.locator("#deeper").click()
    frame.locator("h1:has-text('Deeper')").wait_for()
    page.click("#browseclose")
    page.wait_for_selector("#browse", state="hidden")


def test_the_back_button_closes_the_panel(page, web):
    # On a phone this is the gesture people actually use, and without the
    # history entry it would leave the app instead.
    page.goto(web().url)
    page.wait_for_function("!!window.vivavoce")
    page.click("#material")
    page.wait_for_selector("#browse:not([hidden])")
    page.go_back()
    page.wait_for_selector("#browse", state="hidden")
    assert page.is_visible("#mic")


def test_a_locked_kidsafe_device_is_not_shown_the_way_in(page, web, tmp_path):
    page.goto(web(kidsafe=_locked_kidsafe(tmp_path)).url)
    page.wait_for_function("!!window.vivavoce")
    page.wait_for_selector("#material", state="hidden")
