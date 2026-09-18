"""``pro/vosk_wake.py``: the free-phrase server engine.

Two tiers, because they cost differently. The first needs nothing installed
and covers the part that has burnt this repo before — an engine that reports
itself available and then fails on every chunk (see the docstring of
``ServerWakeWordSessions.available``). The second needs the real ``vosk``
package and a real model on disk, and is the only place the lexicon check can
be shown to actually work: it reads a warning the Kaldi C++ layer writes to
file descriptor 2, which no fake can reproduce honestly.
"""

import importlib.util
import os

import pytest

from pro import vosk_wake
from pro.vosk_wake import ServerVoskWakeSessions, resolve_model

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Where tools/sherpa_bench.py leaves it locally — git-ignored, so absent in a
# fresh clone. VIVAVOCE_TEST_VOSK_MODEL points at one fetched elsewhere, which
# is how CI runs the lexicon half for real instead of skipping it: that check
# reads a warning the Kaldi C++ layer writes to fd 2, and a skipped test would
# notice nothing the day a vosk release stops writing it.
BENCH_MODEL = os.environ.get("VIVAVOCE_TEST_VOSK_MODEL") or os.path.join(
    ROOT, ".sherpa-models", "vosk-model-small-it-0.22")


# -- available() must not lie ------------------------------------------------

def test_no_model_directory_means_unavailable(tmp_path):
    # The package can be installed and the engine still have nothing to load.
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path),
                                      phrase="vivavoce")
    assert sessions.model_dir is None
    assert sessions.available() is False


def test_an_unknown_language_means_unavailable(tmp_path):
    sessions = ServerVoskWakeSessions(lang="klingon", data_dir=str(tmp_path),
                                      phrase="vivavoce")
    assert sessions.available() is False


def test_an_empty_phrase_means_unavailable(tmp_path):
    # Nothing to listen for is not a working engine: every chunk would be
    # matched against "" and the answer would be meaningless either way.
    models = tmp_path / "vosk-models" / "vosk-model-small-it-0.22"
    (models / "conf").mkdir(parents=True)
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path),
                                      phrase="   ")
    assert sessions.model_dir is not None      # the model is there
    assert sessions.available() is False        # the phrase is not


def test_a_half_unzipped_model_does_not_count(tmp_path):
    # A directory with the right name but no conf/ loads and then raises deep
    # inside Kaldi; better to say it isn't there.
    (tmp_path / "vosk-models" / "vosk-model-small-it-0.22").mkdir(parents=True)
    assert resolve_model("it", str(tmp_path)) is None


def test_an_explicit_model_path_is_honoured(tmp_path):
    explicit = tmp_path / "somewhere-else"
    (explicit / "conf").mkdir(parents=True)
    assert resolve_model("it", str(tmp_path), str(explicit)) == str(explicit)
    assert resolve_model("it", str(tmp_path), str(tmp_path / "nope")) is None


def test_the_model_name_shown_to_the_house_is_the_language(tmp_path):
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path))
    assert sessions.model == "vosk-it"


# -- the phrase is per-session state -----------------------------------------

class _FakeModel:
    pass


def _sessions_with_fake_model(tmp_path, phrase="vivavoce"):
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path),
                                      phrase=phrase)
    sessions._model = _FakeModel()          # skip the 50 MB load
    sessions.model_dir = str(tmp_path)
    return sessions


def test_sessions_are_per_client(tmp_path):
    sessions = _sessions_with_fake_model(tmp_path)
    a = sessions.get_or_create("phone")
    assert sessions.get_or_create("phone") is a
    assert sessions.get_or_create("tablet") is not a
    sessions.stop("phone")
    assert sessions.get_or_create("phone") is not a


def test_changing_the_phrase_drops_every_open_session(tmp_path):
    # A detector carries its phrase. Without this the house keeps answering to
    # the old one until every device happens to reload.
    sessions = _sessions_with_fake_model(tmp_path)
    old = sessions.get_or_create("phone")
    sessions.set_phrase("ciao impianto")
    new = sessions.get_or_create("phone")
    assert new is not old
    assert new.phrase == "ciao impianto"


def test_idle_sessions_are_swept(tmp_path):
    """POST /wakeword/stop is the polite exit and usually arrives — but a tab
    closed, a phone that slept or a browser killed never sends it, and each
    abandoned session holds a Kaldi recognizer for good."""
    clock = [1000.0]
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path),
                                      phrase="vivavoce", now=lambda: clock[0])
    sessions._model = _FakeModel()
    first = sessions.get_or_create("phone")
    assert "phone" in sessions._sessions

    clock[0] += vosk_wake.IDLE_SESSION_SECONDS + 1
    sessions.get_or_create("tablet")         # any later chunk sweeps
    assert "phone" not in sessions._sessions
    assert "tablet" in sessions._sessions
    assert sessions.get_or_create("phone") is not first


def test_the_number_of_sessions_has_a_ceiling_not_just_a_clock(tmp_path):
    """The idle cutoff is a clock: inside two minutes, a caller that invents a
    client id per request gets a Kaldi recogniser per request, and the id
    comes straight from the request. So the count is capped too, and what
    goes is whatever was heard from least recently.
    """
    clock = [1000.0]
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path),
                                      phrase="vivavoce", now=lambda: clock[0])
    sessions._model = _FakeModel()
    for i in range(vosk_wake.MAX_SESSIONS + 10):
        clock[0] += 0.1                      # all well inside the idle window
        sessions.get_or_create(f"client-{i}")
    assert len(sessions._sessions) <= vosk_wake.MAX_SESSIONS
    assert len(sessions._seen) <= vosk_wake.MAX_SESSIONS
    # The oldest went, the newest stayed.
    assert "client-0" not in sessions._sessions
    last = f"client-{vosk_wake.MAX_SESSIONS + 9}"
    assert last in sessions._sessions


def test_a_session_that_keeps_streaming_is_kept(tmp_path):
    # The other half: the sweep must not evict a client that is still talking.
    clock = [1000.0]
    sessions = ServerVoskWakeSessions(lang="it", data_dir=str(tmp_path),
                                      phrase="vivavoce", now=lambda: clock[0])
    sessions._model = _FakeModel()
    first = sessions.get_or_create("phone")
    for _ in range(4):
        clock[0] += vosk_wake.IDLE_SESSION_SECONDS / 2
        assert sessions.get_or_create("phone") is first


# -- with the real engine ----------------------------------------------------

# Marks, NOT pytest.importorskip at module scope. importorskip raises Skipped
# during *import*, so it skips the whole file — the nine tests ABOVE it
# included, which need nothing installed and cover the failure this module
# exists to prevent: an engine that reports itself available and then fails on
# every chunk. On any machine without the group they were vanishing in
# silence while the docstring promised two tiers.
_HAS_VOSK = importlib.util.find_spec("vosk") is not None
needs_vosk = pytest.mark.skipif(
    not _HAS_VOSK,
    reason="vosk not installed (uv sync --group wakeword-vosk)")
needs_model = pytest.mark.skipif(
    not _HAS_VOSK or not os.path.isdir(BENCH_MODEL),
    reason=f"no vosk package, or no model at {BENCH_MODEL}")


@needs_vosk
def test_available_is_true_when_the_package_is_installed():
    assert vosk_wake.available() is True


@pytest.fixture(scope="module")
def real_sessions():
    if not _HAS_VOSK or not os.path.isdir(BENCH_MODEL):
        pytest.skip("no vosk package, or no model")
    return ServerVoskWakeSessions(lang="it", data_dir="", phrase="vivavoce",
                                  explicit_model=BENCH_MODEL)


@needs_model
def test_a_real_word_is_in_the_lexicon(real_sessions):
    assert real_sessions.out_of_vocabulary("vivavoce") == []


@needs_model
def test_ordinary_brand_names_are_in_the_lexicon_too(real_sessions):
    # The limit is narrower than "only Italian dictionary words": these are
    # what a household would plausibly pick, and they all pass.
    for phrase in ("alexa", "sonos", "jarvis"):
        assert real_sessions.out_of_vocabulary(phrase) == [], phrase


@needs_model
@pytest.mark.parametrize("phrase", ["zorblax", "qwertzuiop"])
def test_an_invented_name_is_reported_missing(real_sessions, phrase):
    # The whole reason POST /wakeword/phrase refuses: this phrase does not
    # detect badly, it detects at 0%, and nothing else would say so.
    assert real_sessions.out_of_vocabulary(phrase) == [phrase]


@needs_model
def test_only_the_missing_word_of_a_phrase_is_named(real_sessions):
    assert real_sessions.out_of_vocabulary("ciao zorblax") == ["zorblax"]


@needs_model
def test_silence_never_triggers(real_sessions):
    det = real_sessions.get_or_create("test-silence")
    silence = b"\x00\x00" * int(vosk_wake.SAMPLE_RATE * 0.32)
    for _ in range(10):
        assert det.process(silence) is False


@needs_model
def test_an_empty_chunk_is_a_safe_no_op(real_sessions):
    assert real_sessions.get_or_create("test-empty").process(b"") is False


@needs_model
def test_reset_lets_the_same_phrase_fire_again(real_sessions):
    det = real_sessions.get_or_create("test-reset")
    det.process(b"\x00\x00" * 1600)
    det._seen = "vivavoce"          # as if it had just judged this text
    det.reset()
    assert det._seen == ""
