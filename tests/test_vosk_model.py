"""``pro/vosk_model.py``: fetching the wake-word model at start-up.

No test in this repo may touch the network, so ``ensure_model`` takes its
opener. What is worth asserting is not the happy path — it is that every way
this can fail leaves the data directory exactly as it found it, because the
failure mode that matters is a half-unpacked model: it passes
``looks_like_model``, the server announces a working engine, and Kaldi then
raises on every 320 ms chunk for the rest of the session. That is the bug this
module is shaped around.
"""

import io
import os
import urllib.error
import zipfile

import pytest

from pro import vosk_model
from pro.vosk_wake import looks_like_model, models_dir

MODEL_NAME = "vosk-model-small-it-0.22"


def _zip_bytes(names):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, b"x")
    return buf.getvalue()


GOOD_ZIP = _zip_bytes([f"{MODEL_NAME}/conf/model.conf",
                       f"{MODEL_NAME}/am/final.mdl"])


class _Response:
    def __init__(self, payload):
        self._body = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def read(self, n=-1):
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(payload=GOOD_ZIP, error=None):
    calls = []

    def open_url(url, timeout=None):
        calls.append(url)
        if error:
            raise error
        return _Response(payload)

    open_url.calls = calls
    return open_url


def _logged(tmp_path, opener, lang="it"):
    lines = []
    result = vosk_model.ensure_model(lang, str(tmp_path), log=lines.append,
                                     opener=opener)
    return result, "\n".join(lines)


def _leftovers(tmp_path):
    parent = models_dir(str(tmp_path))
    return sorted(os.listdir(parent)) if os.path.isdir(parent) else []


# -- the happy path ----------------------------------------------------------

def test_downloads_and_unpacks(tmp_path):
    opener = _opener()
    path, log = _logged(tmp_path, opener)
    assert path == os.path.join(models_dir(str(tmp_path)), MODEL_NAME)
    assert looks_like_model(path)
    assert opener.calls == [f"{vosk_model.BASE_URL}/{MODEL_NAME}.zip"]
    assert "~50 MB" in log        # says why the wait is happening


def test_an_existing_model_is_not_downloaded_again(tmp_path):
    target = tmp_path / "vosk-models" / MODEL_NAME / "conf"
    target.mkdir(parents=True)
    opener = _opener()
    path, _ = _logged(tmp_path, opener)
    assert path == str(target.parent)
    assert opener.calls == []     # no network at all on the second start


def test_nothing_is_left_lying_around_after_a_success(tmp_path):
    _logged(tmp_path, _opener())
    assert _leftovers(tmp_path) == [MODEL_NAME]   # no scratch, no .zip


# -- every failure leaves the directory as it was ----------------------------

def test_an_unknown_language_is_reported_not_attempted(tmp_path):
    opener = _opener()
    path, log = _logged(tmp_path, opener, lang="klingon")
    assert path is None
    assert opener.calls == []
    assert "klingon" in log and "it" in log      # names what IS available


def test_a_network_failure_leaves_no_model(tmp_path):
    path, log = _logged(tmp_path, _opener(error=urllib.error.URLError("down")))
    assert path is None
    assert _leftovers(tmp_path) == []
    assert "riprovo al prossimo avvio" in log
    assert vosk_model.BASE_URL in log           # so it can be fetched by hand


def test_a_corrupt_archive_leaves_no_model(tmp_path):
    path, _ = _logged(tmp_path, _opener(payload=b"this is not a zip"))
    assert path is None
    assert _leftovers(tmp_path) == []


def test_an_archive_without_the_model_leaves_no_model(tmp_path):
    # A bumped upstream version unpacks to a differently-named directory. That
    # must not publish a directory that only half-exists.
    path, _ = _logged(tmp_path, _opener(_zip_bytes(["something-else/conf/x"])))
    assert path is None
    assert _leftovers(tmp_path) == []


def test_the_model_directory_is_never_partially_published(tmp_path):
    # The property all of the above are really about, asserted directly.
    for payload in (b"not a zip", _zip_bytes(["wrong-name/conf/x"])):
        _logged(tmp_path, _opener(payload=payload))
        target = os.path.join(models_dir(str(tmp_path)), MODEL_NAME)
        assert not looks_like_model(target)


def test_it_publishes_over_a_half_unpacked_leftover(tmp_path):
    # The case reachable through the recovery this module's own failure
    # message recommends ("scarica a mano ... in <parent>"): an interrupted
    # unzip leaves the model directory present but without conf/. It does not
    # look like a model, so the download runs — and os.replace onto a
    # non-empty directory raises ENOTEMPTY, so before the fix the publish
    # failed on EVERY subsequent start-up, reported as "non scaricato" with
    # nothing pointing at the real cause.
    leftover = tmp_path / "vosk-models" / MODEL_NAME
    (leftover / "am").mkdir(parents=True)
    (leftover / "am" / "half.mdl").write_bytes(b"truncated")
    assert not looks_like_model(str(leftover))     # the state that starts it

    path, _ = _logged(tmp_path, _opener())
    assert path == str(leftover)
    assert looks_like_model(path)
    # The leftover is gone, not merged into the new model.
    assert not (leftover / "am" / "half.mdl").exists()
    assert _leftovers(tmp_path) == [MODEL_NAME]


def test_a_complete_model_is_never_re_downloaded_over(tmp_path):
    # The other side of that rmtree: it must only ever fire on the way to
    # publishing a model that was actually fetched, never on a good one.
    good = tmp_path / "vosk-models" / MODEL_NAME
    (good / "conf").mkdir(parents=True)
    (good / "conf" / "model.conf").write_bytes(b"mine")
    opener = _opener()
    path, _ = _logged(tmp_path, opener)
    assert opener.calls == []
    assert (good / "conf" / "model.conf").read_bytes() == b"mine"
    assert path == str(good)


# -- the archive is not trusted ----------------------------------------------

def test_a_member_escaping_the_directory_is_refused(tmp_path):
    evil = _zip_bytes([f"{MODEL_NAME}/conf/x", "../../etc/passwd"])
    path, log = _logged(tmp_path, _opener(payload=evil))
    assert path is None
    assert _leftovers(tmp_path) == []
    assert not (tmp_path.parent / "etc" / "passwd").exists()
    # Named, not merely absent: an archive that simply lacks the model also
    # returns None, so without this the test would pass on an unpacked
    # traversal just as happily as on a refused one.
    assert "archivio sospetto" in log


@pytest.mark.parametrize("member", ["/absolute/x", "a/../../../outside"])
def test_other_traversal_shapes_are_refused_too(tmp_path, member):
    # zipfile stores all three verbatim (checked), so each really does reach
    # the guard rather than being normalised into harmlessness on the way in.
    path, log = _logged(tmp_path, _opener(payload=_zip_bytes([member])))
    assert path is None
    assert "archivio sospetto" in log


# -- the table it works from -------------------------------------------------

def test_every_language_has_a_url(tmp_path):
    from pro.vosk_wake import MODEL_DIRNAMES
    assert set(vosk_model.MODEL_URLS) == set(MODEL_DIRNAMES)
    for lang, url in vosk_model.MODEL_URLS.items():
        assert url.endswith(f"{MODEL_DIRNAMES[lang]}.zip"), lang
        assert url.startswith("https://"), lang
