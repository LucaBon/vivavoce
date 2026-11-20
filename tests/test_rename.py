"""A misheard name, tried again with a name this household really has
(step 1c of docs/name-recognition-design.md).

The case that started it: Edge, asked for Italian, writes «metti camin» for
«metti Kamin». The library finds three songs with «camin» in the title and
asks which — none of them the one meant. Kamin, by EMIN & JONY, has been
played here before, and sounds exactly like «camin».

Most of this file is about when NOT to do it: a typed name, a turn that
played, a list that already holds the name, a guess that finds nothing.
"""

import pytest

from pro.name_index import NameIndex
from pro.names import Names, _decide

OCCITAN = [
    {"id": 1, "title": "Suu Camin de Sent Jacques", "artist": "Cocanha"},
    {"id": 2, "title": "Djal Bai Si Camin", "artist": "Antonio dos Santos"},
    {"id": 3, "title": "Seguissèm lo nòstre camin", "artist": "La Mal Coiffée"},
]
KAMIN = {"id": 9, "title": "Kamin", "artist": "EMIN & JONY"}


class _License:
    def __init__(self, pro=True):
        self.pro = pro

    def is_pro(self):
        return self.pro


def _catalog(transport, by_search):
    """The local library: what each ``titles`` search answers. Albums and
    artists answer nothing, so every request lands on a track."""
    def titles(cmd):
        term = next((p[len("search:"):] for p in cmd if str(p).startswith("search:")), "")
        return {"titles_loop": by_search.get(term.lower(), [])}
    transport.responses["titles"] = titles
    transport.responses["albums"] = {"albums_loop": []}
    transport.responses["artists"] = {"artists_loop": []}


def _names(tmp_path, *played, pro=True):
    index = NameIndex(str(tmp_path / "name_index.json"))
    for title, artist in played:
        index.add_played(title, artist)
    return Names(index, _License(pro), spawn=lambda fn, *a: None)


def _say(srv, text, *, via="voice", alternatives=None):
    body = {"text": text, "via": via, "source": "local", "client": "c1"}
    if alternatives:
        body["alternatives"] = alternatives
    return srv.json_post("/api/v1/command", body)


def _played_ids(transport):
    return [p for cmd in transport.commands() if cmd[:1] == ["playlistcontrol"]
            for p in cmd if str(p).startswith("track_id:")]


@pytest.fixture
def library(transport):
    _catalog(transport, {"camin": OCCITAN, "kamin": [KAMIN]})
    return transport


def test_a_misheard_name_plays_the_known_one(live_server, library, tmp_path):
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "metti camin")
    assert reply["ok"] is True
    assert reply["speech"].startswith("Ho sentito «camin». ")
    assert "Kamin" in reply["speech"]
    assert reply["used"] == "metti Kamin"
    assert reply["choices"] == [] and reply["needs_choice"] is False
    assert _played_ids(library) == ["track_id:9"]


def test_the_list_it_replaced_is_closed(live_server, library, tmp_path):
    """The first answer opened a list of three Occitan songs. Kamin played
    instead; «metti la 2» must not then reach into a list nobody was shown."""
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    _say(srv, "metti camin")
    _say(srv, "metti la 2")
    assert "track_id:2" not in _played_ids(library)


def test_a_typed_name_is_never_touched(live_server, library, tmp_path):
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "metti camin", via="typed")
    assert reply["needs_choice"] is True
    assert len(reply["choices"]) == 3
    assert _played_ids(library) == []


def test_without_pro_the_answer_is_the_ordinary_one(live_server, library, tmp_path):
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY"), pro=False))
    reply = _say(srv, "metti camin")
    assert reply["needs_choice"] is True
    assert _played_ids(library) == []


def test_without_the_feature_the_answer_is_the_ordinary_one(live_server, library):
    reply = _say(live_server(), "metti camin")
    assert reply["needs_choice"] is True


def test_an_unknown_name_leaves_the_list(live_server, library, tmp_path):
    srv = live_server(names=_names(tmp_path, ("Time", "Pink Floyd")))
    reply = _say(srv, "metti camin")
    assert reply["needs_choice"] is True
    assert len(reply["choices"]) == 3


def test_a_list_that_already_holds_the_name_is_a_fair_question(
        live_server, library, tmp_path):
    """Played before, and on the list: the list asked the right question, and
    choosing is the user's — history is not a licence to answer for them."""
    srv = live_server(names=_names(tmp_path, ("Djal Bai Si Camin",
                                              "Antonio dos Santos")))
    reply = _say(srv, "metti camin")
    assert reply["needs_choice"] is True
    assert _played_ids(library) == []


def test_a_turn_that_played_is_never_overruled(live_server, transport, tmp_path):
    """«camin» found one song, and played it. Kamin is known and sounds the
    same — and it does not matter: the request was answered."""
    _catalog(transport, {"camin": [{"id": 5, "title": "Camin", "artist": "X"}],
                         "kamin": [KAMIN]})
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "metti camin")
    assert reply["ok"] is True
    assert not reply["speech"].startswith("Ho sentito")
    assert _played_ids(transport) == ["track_id:5"]


def test_a_guess_that_finds_nothing_keeps_the_first_answer(
        live_server, transport, tmp_path):
    """Known, but no longer in the library: the three Occitan songs are
    still the answer, and their list still works."""
    _catalog(transport, {"camin": OCCITAN})
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "metti camin")
    assert reply["needs_choice"] is True
    assert not reply["speech"].startswith("Ho sentito")
    _say(srv, "metti la 2")
    assert _played_ids(transport) == ["track_id:2"]


def test_a_miss_is_tried_again_too(live_server, transport, tmp_path):
    _catalog(transport, {"kamin": [KAMIN]})  # «camin» finds nothing at all
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "metti camin")
    assert reply["ok"] is True
    assert _played_ids(transport) == ["track_id:9"]


def test_a_sentence_that_is_not_a_play_is_left_alone(live_server, library, tmp_path):
    srv = live_server(names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "blablabla camin")
    assert not reply["speech"].startswith("Ho sentito")
    assert _played_ids(library) == []


def test_the_history_records_the_play_it_made(live_server, library, tmp_path):
    names = _names(tmp_path, ("Kamin", "EMIN & JONY"))
    seen = []
    names.note_played = lambda client, terms: seen.append(list(terms))
    _say(live_server(names=names), "metti camin")
    assert seen == [["Kamin"]]


# -- the decision itself ---------------------------------------------------------

def _e(title, artist=None, kind="track"):
    return {"title": title, "artist": artist, "kind": kind}


def test_below_the_threshold_nothing_is_decided():
    assert _decide([(0.8, _e("Eminem"))], heard_artist=False) is None


def test_two_different_names_that_both_fit_are_a_question():
    ranked = [(1.0, _e("Kamin", "EMIN & JONY")), (0.95, _e("Camin", "Other"))]
    assert _decide(ranked, heard_artist=False) is None


def test_the_same_title_by_two_artists_is_still_an_answer_about_the_title():
    ranked = [(1.0, _e("Kamin", "EMIN & JONY")), (1.0, _e("Kamin", "Someone"))]
    assert _decide(ranked, heard_artist=False) == {"title": "Kamin", "artist": None}
    assert _decide(ranked, heard_artist=True) is None


def test_the_same_song_kept_twice_is_one_name():
    ranked = [(1.0, _e("Kamin", "EMIN & JONY")), (1.0, _e("kamin", "emin & jony"))]
    assert _decide(ranked, heard_artist=False)["title"] == "Kamin"


def test_rename_says_the_artist_only_when_one_was_heard(tmp_path):
    names = _names(tmp_path, ("Kamin", "EMIN & JONY"))
    assert names.rename(["camin"])["text"] == "Kamin"
    assert names.rename(["camin di emin e jony"])["text"] == "Kamin di EMIN & JONY"


def test_rename_skips_a_query_it_would_not_change(tmp_path):
    names = _names(tmp_path, ("Kamin", "EMIN & JONY"))
    assert names.rename(["kamin"]) is None


def test_rename_tries_the_alternatives_in_order(tmp_path):
    names = _names(tmp_path, ("Kamin", "EMIN & JONY"))
    found = names.rename(["vasco rossi", "camin"])
    assert (found["index"], found["text"]) == (1, "Kamin")


@pytest.mark.parametrize("blocked", ["Kamin", "EMIN & JONY"])
def test_a_known_name_does_not_get_past_kid_safe(live_server, library, tmp_path,
                                                 blocked):
    """The rewritten sentence runs through the whole router, guard included:
    a blocked song does not play because the history knew how to spell it."""
    from conftest import FakeLicense
    from pro.kidsafe import KidSafe

    ks = KidSafe(str(tmp_path), FakeLicense(pro=True))
    assert ks.enable("123456", "parent")["ok"]
    ks.store.put([blocked])
    srv = live_server(kidsafe=ks, names=_names(tmp_path, ("Kamin", "EMIN & JONY")))
    reply = _say(srv, "metti camin")
    assert "track_id:9" not in _played_ids(library)
    assert reply["ok"] is False or reply["needs_choice"] is True
