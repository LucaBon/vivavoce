"""The page's half of phase 2 (docs/name-recognition-design.md): the
"remember" offer under a typed answer that corrected a spoken one, and the
settings section beside kid-safe.

The server decides when to offer and what a correction does (that is
tests/test_corrections.py); these check that the page shows the offer, keeps
nothing without a tap, sends what it heard when a transcript was corrected
in the box, and drives the section.
"""

import pytest

from pro.corrections import Corrections
from pro.name_index import NameIndex
from pro.names import Names

HEARD = "metti coming di eminem e johnny"
MEANT = "metti Kamin di EMIN & JONY"

FAKE_HEARS = """
    window.__heard = %r;
    class FakeSR {
      constructor() { this.continuous = false; this.lang = ""; }
      start() {
        setTimeout(() => this.onstart && this.onstart(), 0);
        setTimeout(() => {
          const r = Object.assign([{ transcript: window.__heard }], { isFinal: true });
          this.onresult && this.onresult({ resultIndex: 0, results: [r] });
        }, 20);
        setTimeout(() => this.onend && this.onend(), 40);
      }
      stop() {}
      abort() {}
    }
    window.SpeechRecognition = FakeSR;
    window.webkitSpeechRecognition = FakeSR;
    localStorage.setItem('reclang', 'it');
    localStorage.setItem('source', 'local');
    localStorage.setItem('pro_hint', '1');
""" % HEARD


class _License:
    def __init__(self, pro=True):
        self.pro = pro

    def is_pro(self):
        return self.pro

    def status(self):
        return {"pro": self.pro}


@pytest.fixture
def feature(tmp_path):
    return Names(NameIndex(str(tmp_path / "n.json")), _License(),
                 corrections=Corrections(str(tmp_path / "c.json")),
                 spawn=lambda fn, *a: None)


@pytest.fixture
def library(transport):
    eminem = {"id": 4, "title": "Coming di Eminem e Johnny (Live)", "artist": "Eminem"}
    kamin = {"id": 9, "title": "Kamin", "artist": "EMIN & JONY"}

    def titles(cmd):
        term = next((p[7:] for p in cmd if str(p).startswith("search:")), "").lower()
        return {"titles_loop": {"coming di eminem e johnny": [eminem],
                                "kamin di emin & jony": [kamin]}.get(term, [])}
    transport.responses["titles"] = titles
    transport.responses["albums"] = {"albums_loop": []}
    transport.responses["artists"] = {"artists_loop": []}
    return transport


def _open(page, web, feature, *, pro=True):
    srv = web(license_mgr=_License(pro), names=feature)
    page.add_init_script(FAKE_HEARS)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    return srv


def _autosend(page, on):
    page.evaluate("""on => { const c = document.getElementById('autosend');
                             c.checked = on; c.dispatchEvent(new Event('change')); }""", on)


def _replies(page, n):
    page.wait_for_function(
        "n => document.querySelectorAll('.sys:not(.pending)').length >= n", arg=n)


def test_a_typed_correction_offers_to_remember_and_keeps_it_on_a_tap(
        page, web, feature, library):
    _open(page, web, feature)
    _autosend(page, True)
    page.click("#mic")                      # «coming di eminem e johnny»: plays Eminem
    _replies(page, 1)
    page.fill("#text", MEANT)
    page.click("#send")
    chip = page.locator("button.remember")
    chip.wait_for()
    assert "coming di eminem e johnny" in chip.inner_text()
    assert "Kamin di EMIN & JONY" in chip.inner_text()
    assert feature.corrections.items() == []   # an offer keeps nothing...
    chip.click()
    page.wait_for_function(
        "document.querySelector('button.remember').textContent.includes('✓')")
    [kept] = feature.corrections.items()       # ...until it is tapped
    assert (kept["heard"], kept["meant"]) == ("coming di eminem e johnny",
                                              "Kamin di EMIN & JONY")


def test_a_transcript_corrected_in_the_box_sends_what_was_heard(
        page, web, feature, library):
    bodies = []
    page.on("request", lambda req: bodies.append(req.post_data_json)
            if req.url.endswith("/api/v1/command") else None)
    _open(page, web, feature)
    _autosend(page, False)
    page.click("#mic")
    page.wait_for_function(f"document.getElementById('text').value === {HEARD!r}")
    page.fill("#text", MEANT)
    page.click("#send")
    page.locator("button.remember").wait_for()
    assert bodies[-1]["via"] == "typed"
    assert bodies[-1]["heard"] == [HEARD]


def test_the_section_is_hidden_without_pro(page, web, tmp_path):
    names = Names(NameIndex(str(tmp_path / "n.json")), _License(pro=False),
                  corrections=Corrections(str(tmp_path / "c.json")))
    _open(page, web, names, pro=False)
    page.wait_for_timeout(300)
    assert not page.is_visible("#namesbox")


def test_the_section_shows_and_changes_the_state(page, web, feature):
    feature.index.add_played("Kamin", "EMIN & JONY")
    feature.corrections.add("coming di eminem e johnny", "Kamin di EMIN & JONY")
    _open(page, web, feature)
    page.evaluate("document.getElementById('settings').open = true")
    page.wait_for_function("getComputedStyle(document.getElementById('namesbox'))"
                           ".display !== 'none'")
    assert page.is_checked("#nmhistory")
    assert "1" in page.inner_text("#nmcount")
    assert "Kamin di EMIN & JONY" in page.inner_text("#nmlist")

    page.uncheck("#nmhistory")
    page.wait_for_function("() => true")
    for _ in range(40):
        if not feature.index.history_enabled:
            break
        page.wait_for_timeout(50)
    assert feature.index.history_enabled is False

    page.once("dialog", lambda d: d.accept())
    page.click("#nmclear")
    page.wait_for_function("document.getElementById('nmclear').disabled")
    assert feature.index.history() == []

    page.click("#nmlist button")
    page.wait_for_function("!document.querySelector('#nmlist button')")
    assert feature.corrections.items() == []


def test_clearing_asks_first(page, web, feature):
    feature.index.add_played("Kamin", "EMIN & JONY")
    _open(page, web, feature)
    page.evaluate("document.getElementById('settings').open = true")
    page.wait_for_function("!document.getElementById('nmclear').disabled")
    page.once("dialog", lambda d: d.dismiss())
    page.click("#nmclear")
    page.wait_for_timeout(300)
    assert len(feature.index.history()) == 1
