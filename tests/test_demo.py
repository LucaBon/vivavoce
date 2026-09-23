"""The public demo: the real Router on a hi-fi that exists only in memory.

``docs/demo/`` runs in the browser under Pyodide, so what it imports from
``engine/`` and ``localvoice/`` is the product itself, not a copy. What is the
demo's own is the pretend hi-fi (``hifi.py``) and the few lines that hand it to
the Router (``boot.py``) — and those are what this file holds to account, under
CPython, where a failure is a stack trace rather than a blank page.

The point of the page is one promise: **never the wrong track in silence.** So
the tests that matter here are the ones where the catalogue has *almost* what
was asked for — two songs called «Time», a song it has not got — and the
answer must be the right record or an honest sentence, never the first hit.
"""

import os
import sys

import pytest

from messages import msg

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(REPO_ROOT, "docs", "demo")
sys.path.insert(0, DEMO_DIR)

import boot  # noqa: E402
from hifi import DemoHifi  # noqa: E402


@pytest.fixture
def hifi():
    return DemoHifi(now=lambda: 1000.0)


@pytest.fixture
def demo(hifi):
    return boot.Demo(hifi)


def played(hifi):
    """Every URL the hi-fi was told to start, in order."""
    return [args[0] for name, args in hifi.calls if name == "play_url"]


def test_the_pretend_hifi_keeps_every_promise_a_real_one_must():
    from test_player_protocol import TRANSPORT_ALWAYS, unkept_promises

    hifi = DemoHifi()
    missing = [m for m in TRANSPORT_ALWAYS if not callable(getattr(hifi, m, None))]
    assert missing == []
    assert unkept_promises(hifi.capabilities, hifi) == {}


def test_it_names_no_streaming_service():
    # A service on the client would make playback.after_play wait 0.6 s for
    # a confirmation, and put «da TIDAL» in a reply about a catalogue that
    # is not TIDAL. The demo has neither.
    assert getattr(DemoHifi(), "service", None) is None
    assert not DemoHifi().capabilities.services


def test_a_search_for_nothing_it_has_answers_nothing(hifi):
    # The ranking is trusted only when an empty answer is possible: a search
    # that always returns something would make the engine play tracks[0].
    assert hifi.search_tracks("Wish You Were Here") == []
    assert hifi.search_tracks("Money for Nothing") == []
    assert hifi.search_tracks("") == []


def test_a_record_ends_and_the_next_one_starts():
    clock = [1000.0]
    hifi = DemoHifi(now=lambda: clock[0])
    hifi.play_browse_item(hifi.url_of("Breathe", "Pink Floyd").replace(
        "track/3", "2/The Dark Side of the Moon"))
    assert hifi.now_playing_info()["title"] == "Time"
    clock[0] += 413 + 5
    now = hifi.now_playing_info()
    assert (now["title"], now["index"]) == ("Money", 1)
    assert now["elapsed"] == pytest.approx(5.0)
    clock[0] += 382 + 163
    assert hifi.now_playing_info()["mode"] == "stop"


def test_next_on_the_last_record_stops_like_a_real_player(hifi):
    hifi.play_url(hifi.url_of("Money", "Pink Floyd"))
    hifi.next_track()
    assert hifi.status_info()["mode"] == "stop"


def test_nothing_to_play_leaves_it_stopped(hifi):
    hifi.play_browse_item("demo://2/No Such Album")
    assert hifi.status_info()["mode"] == "stop"
    hifi.add_url(hifi.url_of("Money", "Pink Floyd"))
    assert hifi.status_info()["mode"] == "stop"
    hifi.resume()
    assert hifi.status_info()["mode"] == "play"


def test_the_right_time_not_the_first_one(demo, hifi):
    out = demo.turn("metti Time di Hans Zimmer", "it")
    assert out["ok"], out["speech"]
    assert played(hifi) == [hifi.url_of("Time", "Hans Zimmer")]
    assert hifi.now_playing_info()["artist"] == "Hans Zimmer"


def test_a_song_it_has_not_got_is_said_and_not_played(demo, hifi):
    out = demo.turn("metti Wish You Were Here", "it")
    assert not out["ok"]
    assert played(hifi) == []
    assert "Wish You Were Here" in out["speech"]


@pytest.mark.parametrize("phrase", [
    "metti Money dei Beatles", "metti Money for Nothing", "metti Time after Time",
    "metti Time to say goodbye", "metti Money Money Money", "metti Breathe Me",
    "metti Breathe dei Prodigy",
])
def test_a_title_it_nearly_has_starts_nothing(phrase):
    """What a visitor types to catch it out: a famous song that *contains* a
    title on the shelf. A real catalogue has «Money for Nothing» and plays it;
    this one has not got it, and must say so rather than play «Money»."""
    hifi = DemoHifi(now=lambda: 1000.0)
    out = boot.Demo(hifi).turn(phrase, "it")
    assert not out["ok"], out["speech"]
    assert hifi.calls == []


def test_a_bare_title_plays_the_catalogues_first_and_says_whose(demo, hifi):
    # Not a guess made in silence: the reply names the artist, so «metti Time»
    # answered with Pink Floyd's is corrected by «metti Time di Hans Zimmer».
    out = demo.turn("metti Time", "it")
    assert out["speech"] == msg("playing", name="Time di Pink Floyd")


def test_a_list_then_a_number(demo, hifi):
    listing = demo.turn("quali sono i brani di Pink Floyd", "it")
    assert listing["needs_choice"], listing["speech"]
    assert played(hifi) == []
    second = listing["choices"][1]
    out = demo.turn("metti la 2", "it")
    assert out["ok"], out["speech"]
    assert hifi.now_playing_info()["title"] == second["label"]


def test_an_album_by_name(demo, hifi):
    out = demo.turn("metti l'album Inception", "it")
    assert out["ok"], out["speech"]
    assert hifi.now_playing_info()["artist"] == "Hans Zimmer"


def test_no_reply_names_a_service(demo):
    out = demo.turn("metti Time dei Pink Floyd", "it")
    assert out["ok"]
    assert out["speech"] == msg("playing", name="Time di Pink Floyd")


def test_thirty_seconds_forward_moves_the_record(demo, hifi):
    demo.turn("metti Money", "it")
    demo.turn("vai avanti di 30 secondi", "it")
    assert hifi.status_info()["elapsed"] == pytest.approx(30.0)


def test_the_record_plays_on_by_itself():
    clock = [1000.0]
    hifi = DemoHifi(now=lambda: clock[0])
    boot.Demo(hifi).turn("metti Money", "it")
    clock[0] += 12
    assert hifi.status_info()["elapsed"] == pytest.approx(12.0)
    hifi.pause()
    clock[0] += 50
    assert hifi.status_info()["elapsed"] == pytest.approx(12.0)


def test_a_turn_reports_what_the_hifi_was_told(demo):
    out = demo.turn("metti Money", "it")
    assert out["now_playing"]["title"] == "Money"
    assert ["play_url"] == [c["name"] for c in out["told"] if c["name"] == "play_url"]
    again = demo.turn("pausa", "it")
    assert [c["name"] for c in again["told"]] == ["pause"]


def _phrases():
    import json

    with open(os.path.join(DEMO_DIR, "phrases.json"), encoding="utf-8") as f:
        return json.load(f)["langs"]


PHRASES = _phrases()


def _pick_templates():
    import json

    with open(os.path.join(DEMO_DIR, "phrases.json"), encoding="utf-8") as f:
        return json.load(f)["pick"]
STARTS = {"play_url", "play_tracks", "play_browse_item"}


def test_the_page_suggests_the_same_things_in_all_five_languages():
    assert sorted(PHRASES) == ["de", "en", "es", "fr", "it"]
    shapes = {lang: [p["expect"] for p in ps] for lang, ps in PHRASES.items()}
    assert len(set(map(tuple, shapes.values()))) == 1, shapes


@pytest.mark.parametrize("lang", sorted(PHRASES))
def test_every_suggested_phrase_does_what_the_page_promises(lang):
    """In order, on one conversation: «metti la 2» only means something after
    the list before it."""
    demo = boot.Demo(DemoHifi(now=lambda: 1000.0))
    for phrase in PHRASES[lang]:
        out = demo.turn(phrase["say"], lang)
        told = {c["name"] for c in out["told"]}
        said = f"[{lang}] «{phrase['say']}» -> {out['speech']} {sorted(told)}"
        expect = phrase["expect"]
        if expect == "plays":
            assert out["ok"] and told & STARTS, said
        elif expect == "lists":
            assert out["needs_choice"] and out["choices"] and not told, said
        elif expect == "refuses":
            assert not out["ok"] and not told, said
        else:
            assert expect == "controls", said
            assert out["ok"] and told and not told & STARTS, said


def test_a_tap_sends_what_the_app_sends():
    """The numbered buttons send the words the real page sends (chat.js)."""
    import re

    with open(os.path.join(REPO_ROOT, "localvoice", "static", "js", "chat.js"),
              encoding="utf-8") as f:
        app = dict(re.findall(r'(\w\w): \(n\) => "([^"]+)" \+ n', f.read()))
    demo = {lang: t.replace("{n}", "") for lang, t in _pick_templates().items()}
    assert demo == app


@pytest.mark.parametrize("lang", sorted(PHRASES))
def test_a_tap_on_a_number_plays_it(lang):
    hifi = DemoHifi(now=lambda: 1000.0)
    demo = boot.Demo(hifi)
    listing = demo.turn(PHRASES[lang][4]["say"], lang)
    assert listing["needs_choice"], listing["speech"]
    out = demo.turn(_pick_templates()[lang].format(n=3), lang)
    assert out["ok"], out["speech"]
    assert hifi.now_playing_info()["title"] == listing["choices"][2]["label"]


def test_the_page_can_show_the_whole_catalogue():
    rows = boot.catalogue()
    assert {"title": "Time", "artist": "Hans Zimmer", "album": "Inception"} in rows
    assert not any(r["title"] == "Wish You Were Here" for r in rows)


# -- what the page downloads ---------------------------------------------------
REPO = REPO_ROOT


def _tool():
    import importlib.util

    path = os.path.join(REPO, "tools", "demo_core_files.py")
    spec = importlib.util.spec_from_file_location("demo_core_files", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_list_of_core_files_is_what_the_demo_imports():
    tool = _tool()
    assert tool.listed() == tool.expected(), (
        "docs/demo/core-files.json is stale: "
        "uv run python tools/demo_core_files.py")


def test_the_core_comes_from_the_tag_of_the_version_being_released():
    # Not @main: a branch moves, and jsDelivr serves a moved branch from its
    # cache for hours. The tag RELEASING.md puts on the main merge commit is
    # exactly the tree Pages publishes, and it never moves.
    with open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8") as f:
        version = next(line.split('"')[1] for line in f
                       if line.startswith("version"))
    assert _tool().listed()["ref"] == "v" + version


def test_the_list_is_enough_on_its_own(tmp_path):
    """The page has only these files: so run the demo with only these files.

    Every listed file is copied under an empty root beside the demo's own two,
    and a fresh interpreter plays a phrase. A module the list forgot is an
    ImportError here, not a blank page on GitHub Pages.
    """
    import shutil
    import subprocess

    tool = _tool()
    core = tmp_path / "core"
    for rel in tool.listed()["files"]:
        dest = core / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(REPO, rel), dest)
    demo = tmp_path / "demo"
    demo.mkdir()
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    for name in ("boot.py", "hifi.py"):
        shutil.copy(os.path.join(DEMO_DIR, name), demo / name)
    probe = ("import sys; sys.path.insert(0, sys.argv[2]); import boot; "
             "boot.install(sys.argv[1]); "
             "print(boot.Demo().turn_json('metti Time dei Pink Floyd', 'it'))")
    # From a third, empty directory: `-c` puts the cwd on sys.path, and the
    # core root there would hide an import that Pyodide cannot resolve.
    out = subprocess.run([sys.executable, "-c", probe, str(core), str(demo)],
                         capture_output=True, text=True, cwd=str(elsewhere))
    assert out.returncode == 0, out.stderr
    assert '"ok": true' in out.stdout, out.stdout


def test_the_page_downloads_nothing_it_has_no_use_for():
    files = _tool().listed()["files"]
    assert files and all(os.path.isfile(os.path.join(REPO, f)) for f in files)
    for rel in files:
        assert rel.startswith(("engine/", "localvoice/")), rel
        assert not rel.startswith("localvoice/pro/"), rel
        name = rel.rsplit("/", 1)[-1]
        assert name not in {"server.py", "http_api.py", "httpbase.py", "tls.py",
                            "lms.py", "setupserver.py"}, rel


def test_the_browser_tests_fetch_the_pyodide_the_page_loads():
    import importlib.util
    import re

    path = os.path.join(REPO, "tools", "fetch_pyodide.py")
    spec = importlib.util.spec_from_file_location("fetch_pyodide", path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    with open(os.path.join(DEMO_DIR, "demo.js"), encoding="utf-8") as f:
        js = f.read()
    assert re.findall(r'PYODIDE_VERSION = "([^"]+)"', js) == [tool.version()]
    assert "${PYODIDE_VERSION}" in js
