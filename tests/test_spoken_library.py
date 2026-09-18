"""``--library`` at startup: typos stop the app, an outage does not.

And the promise the whole feature rests on: with no ``--library``, nothing is
built, nothing is dialled and nothing is printed.
"""

import argparse
import dataclasses

import pytest

import cli
import spoken_library
from player import registry as player_registry
from player.abs_backend import SPOKEN_LIBRARY as ABS
from player.audiobookshelf import AudiobookshelfError
from player.composite import Composite


def args_for(*argv):
    return cli.build_parser().parse_args(list(argv))


@pytest.fixture(autouse=True)
def no_library_env(monkeypatch):
    for name in ("LIBRARY", "LIBRARY_URL", "LIBRARY_TOKEN"):
        monkeypatch.delenv(f"VIVAVOCE_{name}", raising=False)


class Probes(list):
    """Every probe made, as ``(url, token)``; answers ``answer`` or raises it."""

    answer = [{"id": "lib-a", "name": "Audiolibri"}]

    def __call__(self, url, *, token=None, timeout=3.0):
        self.append((url, token))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def probes(monkeypatch):
    recorder = Probes()
    monkeypatch.setitem(player_registry.LIBRARIES, ABS.name,
                        dataclasses.replace(ABS, probe=recorder))
    return recorder


def test_no_library_builds_probes_and_says_nothing(probes):
    said = []
    assert spoken_library.open_library(args_for(), say=said.append) == (None, "")
    assert probes == [] and said == []


def test_the_defaults_leave_the_library_off():
    args = args_for()
    assert not args.library and not args.library_url and not args.library_token


def test_the_environment_twins_are_read(monkeypatch):
    monkeypatch.setenv("VIVAVOCE_LIBRARY", "audiobookshelf")
    monkeypatch.setenv("VIVAVOCE_LIBRARY_URL", "http://books.local:13378")
    monkeypatch.setenv("VIVAVOCE_LIBRARY_TOKEN", "k")
    args = args_for()
    assert (args.library, args.library_url, args.library_token) == (
        "audiobookshelf", "http://books.local:13378", "k")


def test_a_configured_library_is_built_and_announced(probes):
    said = []
    composite, complaint = spoken_library.open_library(
        args_for("--library", "Audiobookshelf",
                 "--library-url", "http://books.local:13378",
                 "--library-token", "k"), say=said.append)
    assert complaint == ""
    assert isinstance(composite, Composite)
    assert composite.library.base_url == "http://books.local:13378"
    assert probes == [("http://books.local:13378", "k")]
    assert said == ["Audiobookshelf: 1 libreria di libri (Audiolibri)"]


def test_a_catalogue_that_is_down_does_not_stop_the_app(probes):
    probes.answer = AudiobookshelfError("connection refused")
    said = []
    composite, complaint = spoken_library.open_library(
        args_for("--library", "audiobookshelf",
                 "--library-url", "http://books.local:13378",
                 "--library-token", "k"), say=said.append)
    assert complaint == "" and composite is not None
    assert "non risponde" in said[0] and "la musica no" in said[0]


def test_a_bookshelf_answering_nonsense_does_not_stop_the_app(monkeypatch):
    """The whole promise, through the real client rather than a fake probe.

    A 200 whose body is valid JSON but not the object the API documents — a
    captive portal, a reverse proxy's error page — used to reach ``.get()``
    inside the client as an ``AttributeError``. Not a ``PlayerError``, so the
    ``except PlayerError`` below did not catch it, and it came out of
    ``server.main``: the voice assistant refusing to start because a
    bookshelf answered oddly. The probe here is the real one.
    """
    from player.audiobookshelf import AudiobookshelfClient

    monkeypatch.setattr(
        AudiobookshelfClient, "_http_transport",
        lambda self, request: ["this is not an Audiobookshelf"])
    said = []
    composite, complaint = spoken_library.open_library(
        args_for("--library", "audiobookshelf",
                 "--library-url", "http://books.local:13378",
                 "--library-token", "k"), say=said.append)
    assert complaint == "", complaint
    assert composite is not None
    assert "non risponde" in said[0] and "la musica no" in said[0]


def test_a_key_that_sees_no_book_library_is_said_out_loud(probes):
    probes.answer = []
    said = []
    spoken_library.open_library(
        args_for("--library", "audiobookshelf",
                 "--library-url", "http://books.local:13378",
                 "--library-token", "k"), say=said.append)
    assert "nessuna libreria" in said[0]


@pytest.mark.parametrize("argv, words", [
    (("--library", "calibre", "--library-url", "http://x:1",
      "--library-token", "k"), "disponibili: audiobookshelf"),
    (("--library", "audiobookshelf", "--library-token", "k"), "--library-url"),
    (("--library", "audiobookshelf", "--library-url", "books.local",
      "--library-token", "k"), "--library-url"),
    (("--library", "audiobookshelf", "--library-url", "http://x:1"),
     "--library-token"),
    (("--library-url", "http://x:1",), "senza --library"),
])
def test_options_that_cannot_work_stop_the_app(probes, argv, words):
    composite, complaint = spoken_library.open_library(
        args_for(*argv), say=lambda line: None)
    assert composite is None
    assert words in complaint
    assert probes == []


@pytest.mark.parametrize("url", ["http://localhost:13378",
                                 "http://127.0.0.1:13378", "http://[::1]:13378"])
def test_a_loopback_address_is_warned_about_not_refused(probes, url):
    # The hi-fi fetches the files. On another machine, localhost is the hi-fi.
    said = []
    composite, complaint = spoken_library.open_library(
        argparse.Namespace(library="audiobookshelf", library_url=url,
                           library_token="k"), say=said.append)
    assert complaint == "" and composite is not None
    assert "indirizzo locale" in said[0]


def test_a_lan_address_gets_no_warning(probes):
    said = []
    spoken_library.open_library(
        argparse.Namespace(library="audiobookshelf",
                           library_url="http://192.168.1.50:13378",
                           library_token="k"), say=said.append)
    assert not any("indirizzo locale" in line for line in said)
