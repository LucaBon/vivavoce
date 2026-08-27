"""The AI Act art. 50(1) disclosure — that it exists, and that it is reachable.

Article 50(1) of Regulation (EU) 2024/1689 has applied since 2 August 2026 and,
per §153 of the Commission's guidelines (C(2026) 5054 of 20.7.2026), it applies
to every in-scope system on the market "regardless of their date of placement".
Vivavoce is in scope: an AI-enabled voice assistant is the first example the
guidelines list (§3.1.1). The reasoning, and everything that is *not* in scope,
is written down in ``docs/ai-act.md``.

What is left to a test is the part a refactor can quietly undo. The disclosure
is one short line of markup and one call in a UI module: both are the kind of
thing that gets tidied away by somebody who does not know why they are there.
So this file pins the three properties the obligation actually rests on —

* it is *there*, in the interaction area, not filed under a menu (§38 rules out
  disclosures reachable only from documentation or settings);
* it is not conditional — no state, no toggle, no media query hides it;
* it exists in both languages the app speaks, on screen and out loud.

Wording is deliberately not asserted: it should be free to improve. What may
not change is that something is said, where it can be seen and heard.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(HERE), "localvoice")

NOTICE_KEY = "ai_notice"
SPOKEN_KEY = "ai_notice_spoken"


def _asset(*parts):
    with open(os.path.join(WEB_DIR, *parts), encoding="utf-8") as f:
        return f.read()


def _ui_table(name):
    """The keys of ``UI_EN`` / ``UI_IT`` as written in strings.js."""
    source = _asset("static", "js", "strings.js")
    body = source.split("export const %s = {" % name, 1)[1]
    body = re.split(r"^export const ", body, flags=re.M)[0]
    return set(re.findall(r"^  ([A-Za-z_][A-Za-z0-9_]*)\s*:", body, re.M))


def _hero_markup():
    """Just the sticky top area: the mic, the status line, the text box."""
    page = _asset("index.html")
    start = page.index('<div class="hero">')
    return page[start:page.index('<div class="content">', start)]


# -- on screen -----------------------------------------------------------------

def test_the_page_says_it_is_an_automated_assistant():
    assert 'data-i18n="%s"' % NOTICE_KEY in _asset("index.html")


def test_the_disclosure_sits_with_the_controls_it_describes():
    # §37 puts the notice next to the input/output; §38 refuses one that is
    # only reachable from a menu. The hero is what the page shows before the
    # user scrolls or opens anything.
    assert 'data-i18n="%s"' % NOTICE_KEY in _hero_markup()


def test_the_disclosure_is_not_hidden_by_the_markup():
    # The neighbouring #kschip ships `style="display:none"` and is revealed by
    # script. Copying that pattern here would ship a page whose disclosure is
    # one JavaScript failure away from never appearing.
    line = next(ln for ln in _hero_markup().splitlines()
                if 'data-i18n="%s"' % NOTICE_KEY in ln)
    assert "display:none" not in line.replace(" ", "")
    assert not re.search(r"\bhidden\b", line)


def test_no_stylesheet_rule_hides_the_disclosure():
    css = _asset("static", "css", "app.css")
    for rule in re.findall(r"#ainotice[^{]*\{([^}]*)\}", css):
        assert "display: none" not in rule and "display:none" not in rule
        assert "visibility: hidden" not in rule


def test_no_module_toggles_the_disclosure_off():
    # Nothing should be able to reach in and hide it at runtime either.
    js_dir = os.path.join(WEB_DIR, "static", "js")
    for name in sorted(os.listdir(js_dir)):
        if not name.endswith(".js"):
            continue
        source = _asset("static", "js", name)
        assert "ainotice" not in source, (
            "%s manipulates the art. 50(1) notice; it is meant to be inert "
            "markup that nothing can switch off" % name)


def test_the_served_page_carries_the_disclosure(live_server):
    # Placeholders are substituted at request time: assert on what ships.
    assert 'data-i18n="%s"' % NOTICE_KEY in live_server().get("/").text


# -- in both languages ---------------------------------------------------------

def test_every_markup_label_has_an_english_counterpart():
    # applyUI() falls back to the Italian snapshot when UI_EN lacks a key, so a
    # missing translation is not an error — it is an English page with an
    # Italian sentence in it, which for the disclosure specifically means the
    # notice stops being "easy to understand" for its reader (art. 50(5)).
    keys = set(re.findall(r'data-i18n="([^"]+)"', _asset("index.html")))
    assert keys - _ui_table("UI_EN") == set()


# -- out loud ------------------------------------------------------------------

def test_the_spoken_disclosure_exists_in_both_languages():
    assert SPOKEN_KEY in _ui_table("UI_EN")
    assert SPOKEN_KEY in _ui_table("UI_IT")


def test_the_spoken_disclosure_is_wired_to_the_start_of_listening():
    # micUI() is the single point every engine passes through when a voice
    # session begins (tap-to-talk, Web Speech wake word, server-side wake
    # word). If the call leaves it, hands-free users are never told.
    tts = _asset("static", "js", "tts.js")
    capture = _asset("static", "js", "miccapture.js")
    assert "export function speakAiNotice" in tts
    assert SPOKEN_KEY in tts
    assert "speakAiNotice" in capture
    body = capture.split("export function micUI(", 1)[1].split("\n}", 1)[0]
    assert "speakAiNotice" in body, "the notice is imported but never spoken"


# -- the written record --------------------------------------------------------

ROOT = os.path.dirname(HERE)
# The compliance paper trail: the assessment, the model provenance it cites,
# and the two user-facing docs that now point at them. Kept small on purpose —
# this is the set whose cross-references carry a legal claim, not every .md.
COMPLIANCE_DOCS = [
    os.path.join("docs", "ai-act.md"),
    os.path.join("licenses", "MODELS.md"),
    "README.md",
    "PRIVACY.md",
]


def _doc(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_the_assessment_exists_and_names_the_article_it_answers():
    # §42/§45 put the burden of the assessment on the provider. A disclosure
    # with no reasoning behind it is half the obligation.
    paper = _doc(os.path.join("docs", "ai-act.md"))
    assert "50(1)" in paper


def test_the_compliance_docs_link_to_things_that_exist():
    broken = []
    for rel in COMPLIANCE_DOCS:
        here = os.path.dirname(os.path.join(ROOT, rel))
        for target in re.findall(r"\]\(([^)#\s]+)\)", _doc(rel)):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(here, target))):
                broken.append((rel, target))
    assert broken == []


def test_the_user_facing_docs_point_at_the_assessment():
    # Art. 4 is an obligation of means; the means chosen here is saying plainly
    # what is AI and linking the rest. If the link rots, so does the measure.
    for rel in ("README.md", "PRIVACY.md"):
        assert "docs/ai-act.md" in _doc(rel), "%s no longer points at it" % rel
