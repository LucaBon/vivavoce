"""Whisper told which names to expect (phase 3 of
docs/name-recognition-design.md).

The other phases repair a name after the recogniser wrote it wrong. This one
asks the recogniser not to: faster-whisper takes ``hotwords``, a string of
words it should expect, and the names this household plays are exactly that.

What can be tested without a microphone is tested here — which names, in
what order, how many, and that they reach the engine. Whether they *help* is
a question for real recordings (see the design document).
"""

import io

import pytest

from conftest import FakeLicense
from pro.asr import WhisperTranscriber
from pro.corrections import Corrections
from pro.name_index import NameIndex
from pro.names import MAX_HOTWORDS_CHARS, Names


def _names(tmp_path, pro=True):
    return Names(NameIndex(str(tmp_path / "n.json")), FakeLicense(pro=pro),
                 corrections=Corrections(str(tmp_path / "c.json")),
                 spawn=lambda fn, *a: None)


# -- which names --------------------------------------------------------------------

def test_confirmed_corrections_come_first_then_the_most_played(tmp_path):
    names = _names(tmp_path)
    names.index.add_played("Time", "Pink Floyd")
    for _ in range(3):
        names.index.add_played("Creep", "Radiohead")
    names.corrections.add("coming di eminem e johnny", "Kamin di EMIN & JONY")
    assert names.hotwords("it") == ("Kamin, EMIN & JONY, Creep, Radiohead, "
                                    "Time, Pink Floyd")


def test_each_name_once(tmp_path):
    names = _names(tmp_path)
    names.index.add_played("Kamin", "EMIN & JONY")
    names.index.add_played("Na Rassvete", "EMIN & JONY")
    names.corrections.add("camin", "kamin")
    words = names.hotwords("it").split(", ")
    assert [w.lower() for w in words].count("kamin") == 1
    assert words.count("EMIN & JONY") == 1


def test_a_correction_in_another_language_is_not_a_hint(tmp_path):
    names = _names(tmp_path)
    names.corrections.add("coming", "Kamin", "en")
    assert names.hotwords("it") is None
    assert names.hotwords("en") == "Kamin"


def test_favourites_and_the_library_are_not_hints(tmp_path):
    """Five thousand library artists are not a hint but noise: Whisper would
    start hearing them everywhere."""
    names = _names(tmp_path)
    names.index.set_source("library", [{"artist": "Somebody", "kind": "artist"}])
    names.index.set_source("favorites", [{"title": "Radio Paradise"}])
    assert names.hotwords("it") is None


def test_the_list_is_bounded_and_never_cuts_a_name(tmp_path):
    names = _names(tmp_path)
    for i in range(200):
        names.index.add_played(f"A Rather Long Song Title Number {i}", f"Artist {i}")
    words = names.hotwords("it")
    assert len(words) <= MAX_HOTWORDS_CHARS
    for name in words.split(", "):
        assert name.startswith(("A Rather Long Song Title Number", "Artist"))


def test_nothing_known_is_no_hint(tmp_path):
    assert _names(tmp_path).hotwords("it") is None


def test_without_pro_there_is_no_hint(tmp_path):
    names = _names(tmp_path, pro=False)
    names.index.add_played("Kamin", "EMIN & JONY")
    assert names.hotwords("it") is None


# -- reaching the engine -------------------------------------------------------------

class _Segment:
    text = " metti Kamin "


class _Info:
    duration = 2.0


class _Model:
    """faster-whisper's ``WhisperModel``, as far as transcribe() goes."""

    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        assert isinstance(audio, io.BytesIO)
        self.kwargs = kwargs
        return iter([_Segment()]), _Info()


@pytest.fixture
def whisper():
    t = WhisperTranscriber()
    t._model = _Model()  # loaded already: no package, no download
    return t


def test_whisper_is_given_the_names(whisper):
    assert whisper.transcribe(b"AUDIO", "it", hotwords="Kamin, EMIN & JONY") == {
        "text": "metti Kamin", "alternatives": ["metti Kamin"]}
    assert whisper._model.kwargs["hotwords"] == "Kamin, EMIN & JONY"


def test_no_names_no_argument(whisper):
    """Not even ``hotwords=None``: the call stays the one it always was."""
    whisper.transcribe(b"AUDIO", "it")
    assert "hotwords" not in whisper._model.kwargs


class _Engine:
    model_name = "small"

    def __init__(self, takes_hotwords=True):
        self.calls = []
        self.takes_hotwords = takes_hotwords

    def available(self):
        return True

    def transcribe(self, audio, lang="it", **kw):
        if kw and not self.takes_hotwords:
            raise TypeError("unexpected keyword argument 'hotwords'")
        self.calls.append((lang, kw.get("hotwords")))
        return {"text": "metti Kamin", "alternatives": ["metti Kamin"]}


def _post(srv, lang="it"):
    return srv.post(f"/transcribe?lang={lang}", b"OPUSDATA", "audio/webm").json()


def test_the_endpoint_hands_the_household_s_names_to_the_engine(live_server, tmp_path):
    names = _names(tmp_path)
    names.index.add_played("Kamin", "EMIN & JONY")
    engine = _Engine()
    srv = live_server(transcriber=engine, license_mgr=FakeLicense(pro=True),
                      names=names)
    assert _post(srv)["ok"] is True
    assert engine.calls == [("it", "Kamin, EMIN & JONY")]


def test_with_no_names_the_engine_is_called_as_before(live_server, tmp_path):
    """An engine that predates the argument keeps working when there is
    nothing to hint: the argument is not sent at all."""
    engine = _Engine(takes_hotwords=False)
    srv = live_server(transcriber=engine, license_mgr=FakeLicense(pro=True),
                      names=_names(tmp_path))
    assert _post(srv)["ok"] is True
    assert engine.calls == [("it", None)]


def test_a_failing_name_list_costs_the_hint_not_the_transcription(live_server):
    class _Broken:
        def hotwords(self, lang):
            raise RuntimeError("boom")

    engine = _Engine()
    srv = live_server(transcriber=engine, license_mgr=FakeLicense(pro=True),
                      names=_Broken())
    assert _post(srv)["text"] == "metti Kamin"
    assert engine.calls == [("it", None)]
