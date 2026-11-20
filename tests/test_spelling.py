"""Respellings of a name nobody here has played yet (phase 4 of
docs/name-recognition-design.md).

«camin» is not in the history, so the index cannot help. But a catalogue
keyed by letters may hold the same sound as «Kamin»: the respelling is
looked up — searched, never played — and only a title that comes back
sounding like what was heard is used.
"""

import pytest

from pro.name_index import NameIndex
from pro.names import Names
from pro.phonetic import phonetic_key
from pro.spelling import MAX_VARIANTS, respell, spelling_variants

OCCITAN = [
    {"id": 1, "title": "Suu Camin de Sent Jacques", "artist": "Cocanha"},
    {"id": 2, "title": "Djal Bai Si Camin", "artist": "Antonio dos Santos"},
    {"id": 3, "title": "Seguissèm lo nòstre camin", "artist": "La Mal Coiffée"},
]
KAMIN = {"id": 9, "title": "Kamin", "artist": "EMIN & JONY"}


# -- the respellings ---------------------------------------------------------------

@pytest.mark.parametrize("heard, first", [
    ("camin", "kamin"),
    ("gioni", "jony"),       # every rule at once comes first
    ("chiara", "kiara"),
    ("filip", "philip"),
])
def test_the_likeliest_respelling_comes_first(heard, first):
    assert spelling_variants(heard)[0] == first


def test_every_respelling_sounds_exactly_the_same():
    for heard in ("camin", "gioni", "cuin", "camino dei cuori", "vagner"):
        for variant in spelling_variants(heard, limit=10):
            assert phonetic_key(variant, "it") == phonetic_key(heard, "it")


@pytest.mark.parametrize("heard", ["scena", "lei", "time", "emin e jony", ""])
def test_a_word_with_no_other_spelling_has_none(heard):
    assert spelling_variants(heard) == []


def test_short_words_ending_in_i_are_left_alone():
    """«dei», «lei», «noi» are not «dey»: only a longer word ending in a
    consonant and i is a name that may be spelt with a y."""
    assert all("dey" not in v for v in spelling_variants("camino dei cuori", limit=10))


def test_there_is_a_limit():
    assert len(spelling_variants("camino dei cuori gioni", limit=10)) > MAX_VARIANTS
    assert len(spelling_variants("camino dei cuori gioni")) == MAX_VARIANTS


# -- looking them up -----------------------------------------------------------------

class _Catalogue:
    """A search that plays nothing, and counts."""

    def __init__(self, answers=None, fail=False):
        self.answers = answers or {}
        self.fail = fail
        self.asked = []

    def __call__(self, query):
        self.asked.append(query)
        if self.fail:
            raise OSError("not answering")
        return self.answers.get(query, [])


def test_a_respelling_the_catalogue_holds_is_the_answer():
    search = _Catalogue({"kamin": [KAMIN]})
    found = respell(["camin"], "it", search)
    assert (found["text"], found["title"]) == ("Kamin", "Kamin")
    assert search.asked == ["kamin"]


def test_the_artist_heard_goes_into_the_search_and_the_answer():
    search = _Catalogue({"kamin emin e jony": [KAMIN]})
    found = respell(["camin di emin e jony"], "it", search)
    assert found["text"] == "Kamin di EMIN & JONY"


def test_what_comes_back_has_to_sound_like_what_was_heard():
    """A search that always answers (Spotify does) is not evidence."""
    search = _Catalogue({"kamin": [{"title": "Kaminari", "artist": "Someone"},
                                   {"title": "Something Else", "artist": "X"}]})
    assert respell(["camin"], "it", search) is None


def test_two_titles_that_both_fit_are_a_question():
    search = _Catalogue({"kamin": [{"title": "Kamin", "artist": "A"},
                                   {"title": "Kamin", "artist": "B"}]})
    # No artist heard: still an answer about the title — the search will ask.
    assert respell(["camin"], "it", search)["text"] == "Kamin"
    # An artist heard that fits neither: no answer.
    search = _Catalogue({"kamin nobody": [{"title": "Kamin", "artist": "A"},
                                          {"title": "Kamin", "artist": "B"}]})
    assert respell(["camin di nobody"], "it", search) is None


def test_at_most_a_couple_of_searches_per_request():
    search = _Catalogue()
    # No «di»/«dei» in it: the whole phrase is the title, with many respellings.
    assert respell(["camino cuori gioni"], "it", search) is None
    assert len(search.asked) == MAX_VARIANTS


def test_a_search_that_fails_ends_the_attempt():
    search = _Catalogue(fail=True)
    assert respell(["camin", "gioni"], "it", search) is None
    assert len(search.asked) == 1


def test_without_pro_nothing_is_searched(tmp_path):
    class _NoPro:
        def is_pro(self):
            return False

    search = _Catalogue({"kamin": [KAMIN]})
    names = Names(NameIndex(str(tmp_path / "n.json")), _NoPro())
    assert names.respell(["camin"], "it", search=search) is None
    assert search.asked == []


# -- the router: where it looks, and that it never plays ----------------------------

def _catalog(transport, by_search):
    def titles(cmd):
        term = next((p[7:] for p in cmd if str(p).startswith("search:")), "").lower()
        return {"titles_loop": by_search.get(term, [])}
    transport.responses["titles"] = titles
    transport.responses["albums"] = {"albums_loop": []}
    transport.responses["artists"] = {"artists_loop": []}


def _searched(transport):
    return [p[7:] for cmd in transport.commands() if cmd[:1] == ["titles"]
            for p in cmd if str(p).startswith("search:")]


def _played(transport):
    return [p for cmd in transport.commands() if cmd[:1] == ["playlistcontrol"]
            for p in cmd if str(p).startswith("track_id:")]


class _License:
    def is_pro(self):
        return True


@pytest.fixture
def names(tmp_path):
    """An empty history: nothing has ever been played here."""
    return Names(NameIndex(str(tmp_path / "n.json")), _License(),
                 spawn=lambda fn, *a: None)


def _say(srv, text, via="voice"):
    return srv.json_post("/api/v1/command", {"text": text, "via": via,
                                             "source": "local", "client": "c"})


def test_a_name_never_played_is_found_by_its_respelling(live_server, transport, names):
    _catalog(transport, {"camin": OCCITAN, "kamin": [KAMIN]})
    reply = _say(live_server(names=names), "metti camin")
    assert reply["ok"] is True
    assert reply["speech"].startswith("Ho sentito «camin». ")
    assert reply["used"] == "metti Kamin"
    assert _played(transport) == ["track_id:9"]   # looked up, then played once


def test_typed_it_stays_the_list(live_server, transport, names):
    _catalog(transport, {"camin": OCCITAN, "kamin": [KAMIN]})
    reply = _say(live_server(names=names), "metti camin", via="typed")
    assert reply["needs_choice"] is True
    assert "kamin" not in _searched(transport)


def test_a_turn_that_played_looks_nothing_up(live_server, transport, names):
    _catalog(transport, {"camin": [{"id": 5, "title": "Camin", "artist": "X"}],
                         "kamin": [KAMIN]})
    _say(live_server(names=names), "metti camin")
    assert _played(transport) == ["track_id:5"]
    assert "kamin" not in _searched(transport)


def test_the_streaming_service_is_asked_for_a_streaming_request(lms):
    """``auto`` and a service name look in the catalogue the request would
    have used; ``local`` only in the library."""
    from router import Router

    class _Stream:
        def __init__(self):
            self.asked = []

        def search_tracks(self, query, count=20):
            self.asked.append(query)
            return [{"title": "Kamin", "artist": None}]

    stream = _Stream()
    r = Router(lms)
    r._streaming = lambda source: (stream, "tidal", False)
    assert r._probe_for("tidal")("kamin") == [{"title": "Kamin", "artist": None}]
    assert stream.asked == ["kamin"]
    r._probe_for("local")("kamin")
    assert stream.asked == ["kamin"]          # the library alone, for «local»
