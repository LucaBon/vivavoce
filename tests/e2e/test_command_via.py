"""What the page tells the server about how a sentence arrived.

Only a spoken turn can carry the recogniser's mistakes, and the server
corrects nothing else (docs/name-recognition-design.md), so ``via`` has to be
right in every path that sends a command:

* spoken and sent straight away (auto-send on): ``voice``;
* written in the box: ``typed``;
* spoken, left in the box for a check, and sent untouched: still ``voice`` —
  and it keeps the recogniser's alternatives, which this path used to drop;
* spoken, then corrected in the box before sending: ``typed``. That edit is
  the user writing the name the way it is spelt, and it is exactly the
  correction the name-recognition work learns from.
"""

import pytest

FAKE_HEARS_CAMIN = """
    class FakeSR {
      constructor() { this.continuous = false; this.lang = ""; }
      start() {
        setTimeout(() => this.onstart && this.onstart(), 0);
        setTimeout(() => {
          const r = Object.assign([{ transcript: "metti camin" },
                                   { transcript: "metti kamin" }],
                                  { isFinal: true });
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
    localStorage.setItem('pro_hint', '1');
"""


class _ProLicense:
    def is_pro(self):
        return True

    def status(self):
        return {"pro": True}


@pytest.fixture
def sent(page, web):
    """Open the page and collect the body of every command it sends."""
    bodies = []
    page.on("request", lambda req: bodies.append(req.post_data_json)
            if req.url.endswith("/api/v1/command") else None)
    srv = web(license_mgr=_ProLicense())
    page.add_init_script(FAKE_HEARS_CAMIN)
    page.goto(srv.url)
    page.wait_for_function("!!window.vivavoce")
    return bodies


def _autosend(page, on):
    if page.is_checked("#autosend") != on:
        page.evaluate("""on => { const c = document.getElementById('autosend');
                                 c.checked = on; c.dispatchEvent(new Event('change')); }""",
                      on)


def _wait_for(page, bodies, n):
    for _ in range(50):
        if len(bodies) >= n:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"expected {n} command(s), got {bodies}")


def test_spoken_and_sent_straight_away_is_voice(page, sent):
    _autosend(page, True)
    page.click("#mic")
    _wait_for(page, sent, 1)
    assert sent[0]["via"] == "voice"
    assert sent[0]["alternatives"] == ["metti camin", "metti kamin"]


def test_written_in_the_box_is_typed(page, sent):
    page.fill("#text", "metti Kamin")
    page.click("#send")
    _wait_for(page, sent, 1)
    assert sent[0]["via"] == "typed"


def test_spoken_checked_and_sent_untouched_is_still_voice(page, sent):
    _autosend(page, False)
    page.click("#mic")
    page.wait_for_function("document.getElementById('text').value === 'metti camin'")
    page.click("#send")
    _wait_for(page, sent, 1)
    assert sent[0]["via"] == "voice"
    assert sent[0]["alternatives"] == ["metti camin", "metti kamin"]


def test_spoken_then_corrected_in_the_box_is_typed(page, sent):
    _autosend(page, False)
    page.click("#mic")
    page.wait_for_function("document.getElementById('text').value === 'metti camin'")
    page.fill("#text", "metti Kamin di EMIN")
    page.click("#send")
    _wait_for(page, sent, 1)
    assert sent[0]["via"] == "typed"
    assert "alternatives" not in sent[0]
