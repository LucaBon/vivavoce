"""The AGPL core, started with no ``pro/`` at all.

``licenses/README.md`` presents this repository as open-core: everything but
``localvoice/pro/`` is AGPL-3.0, and the AGPL half is meant to be a working
program on its own. It was not. Four ``pro.*`` imports in ``server.py`` and
``audio_engines.py`` were unguarded (the two from ``server.py`` live in
``pro_features.py`` now), so a checkout of the free half died at
start-up with ``ModuleNotFoundError: No module named 'pro'`` — before the line
that would have said what was missing, and with nothing to do about it.

Nothing downstream needed changing to fix it, which is the interesting part:
``kidsafe=None`` and ``multiroom=None`` are how the Router, the handler and
the setup page have always behaved for a household without a licence. The
imports simply had to be allowed to fail.

The package is hidden rather than deleted: a finder on ``sys.meta_path``
refuses ``pro`` and everything under it, and the modules under test are
re-imported inside that window. That is as close to "this copy has no pro/"
as a test can get without a second checkout — and unlike a second checkout it
stays true, because the import that this file does not know about is the one
it fails on.
"""

import importlib
import subprocess
import sys

import pytest

import appdata
from conftest import FakeLicense


class _NoPro:
    """A meta-path finder that makes ``pro`` and ``pro.*`` unimportable."""

    def find_module(self, name, path=None):          # py2-era hook, harmless
        return self.find_spec(name, path)

    def find_spec(self, name, path=None, target=None):
        if name == "pro" or name.startswith("pro."):
            raise ImportError(f"no module named {name!r} in this build")
        return None


@pytest.fixture
def without_pro():
    """Hide ``pro`` for the duration of a test, modules and all."""
    hidden = {name: mod for name, mod in sys.modules.items()
              if name == "pro" or name.startswith("pro.")}
    for name in hidden:
        del sys.modules[name]
    finder = _NoPro()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(hidden)


class _Args:
    """The handful of ``cli`` fields ``audio_engines.build`` reads."""
    asr_model = None
    wakeword_lang = "it"
    wakeword_no_download = True
    wakeword_vosk_model = ""


def test_kid_safe_is_absent_rather_than_fatal(without_pro, tmp_path):
    import pro_features
    importlib.reload(pro_features)
    assert pro_features.build_kidsafe(str(tmp_path), FakeLicense()) is None


def test_multi_room_is_absent_rather_than_fatal(without_pro, lms):
    import pro_features
    importlib.reload(pro_features)
    assert pro_features.build_multiroom(FakeLicense(), lms) is None


def test_the_audio_engines_all_degrade(without_pro, tmp_path, capsys):
    import audio_engines
    importlib.reload(audio_engines)
    transcriber, wakeword, phrases = audio_engines.build(_Args(), str(tmp_path))
    assert transcriber is None
    assert wakeword is None
    # The wake phrase is household configuration and the browser engine
    # answers to it, so it survives a build with no Pro module at all.
    assert isinstance(phrases, appdata.WakePhraseStore)
    said = capsys.readouterr().out
    assert "non incluso in questa build" in said


def test_the_handler_still_serves_the_page(without_pro, live_server):
    # The other half of the claim: not merely "it imports", but "it answers".
    # kidsafe and multiroom default to None here exactly as ``main`` would
    # now pass them.
    srv = live_server()
    assert srv.get("/").status == 200
    assert srv.json_post("/api/v1/command", {"text": "pausa"})["ok"] is True


#: Every module of the free half, imported from nothing, with ``pro`` refused.
#: Run in a child process on purpose: importing the whole app a second time
#: inside this one would leave two copies of ``appdata`` in ``sys.modules``,
#: and the tests that monkeypatch it would patch the copy nobody uses. A child
#: is also the more honest answer to "does this start with no pro/" — it is
#: the same thing the user would do.
_IMPORT_PROBE = """
import sys
sys.path.insert(0, {engine!r})
sys.path.insert(0, {localvoice!r})


class NoPro:
    def find_spec(self, name, path=None, target=None):
        if name == "pro" or name.startswith("pro."):
            raise ImportError(name)
        return None


sys.meta_path.insert(0, NoPro())
for name in ("server", "pro_features", "audio_engines", "http_api", "api_v1",
             "audio_api", "router", "sources", "intents", "conversation",
             "setupserver", "licensing", "appdata", "staticfiles",
             "lmsproxy"):
    __import__(name)
print("ok")
"""


def test_the_free_half_imports_nothing_from_pro_at_module_scope():
    # Every ``pro.*`` import in the core has to be inside a function AND
    # guarded; this is what says so for the modules, not for one call site.
    from conftest import ENGINE_DIR, LOCALVOICE_DIR

    done = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE.format(
            engine=ENGINE_DIR, localvoice=LOCALVOICE_DIR)],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().endswith("ok")
