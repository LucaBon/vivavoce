"""The index of known names (localvoice/pro/name_index.py) and the feature
that fills it (localvoice/pro/names.py) — step 1b of
docs/name-recognition-design.md.

The router side — that a turn which played something reports it, and one that
did not stays quiet — is at the bottom, through the real HTTP stack.
"""

import json

import pytest

from player.protocols import Capabilities
from pro.name_index import NameIndex
from pro.names import Names, _vouched_for


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "name_index.json")


# -- the history ---------------------------------------------------------------

def test_a_play_is_kept_and_counted(path):
    index = NameIndex(path)
    assert index.add_played("Kamin", "EMIN & JONY")
    assert index.add_played("Kamin", "EMIN & JONY")
    [entry] = index.history()
    assert (entry["title"], entry["artist"], entry["weight"]) == (
        "Kamin", "EMIN & JONY", 2)


def test_the_latest_spelling_wins(path):
    """Same name folded, a catalogue that fixed its capitals: one entry, and
    the spelling the player reports now."""
    index = NameIndex(path)
    index.add_played("kamin", "emin & jony")
    index.add_played("Kamin", "EMIN & JONY")
    [entry] = index.history()
    assert (entry["title"], entry["artist"]) == ("Kamin", "EMIN & JONY")


def test_the_history_survives_a_restart(path):
    NameIndex(path).add_played("Kamin", "EMIN & JONY")
    assert [e["title"] for e in NameIndex(path).history()] == ["Kamin"]


def test_nothing_to_keep_is_not_kept(path):
    index = NameIndex(path)
    assert not index.add_played("", None)
    assert index.history() == []


def test_switched_off_it_keeps_nothing_new_and_forgets_nothing(path):
    index = NameIndex(path)
    index.add_played("Time", "Pink Floyd")
    index.set_history_enabled(False)
    assert not index.add_played("Kamin", "EMIN & JONY")
    assert [e["title"] for e in index.history()] == ["Time"]
    # ...and stays off after a restart.
    assert NameIndex(path).history_enabled is False


def test_it_is_on_by_default(path):
    assert NameIndex(path).history_enabled is True


def test_clearing_empties_it_for_good(path):
    index = NameIndex(path)
    index.add_played("Kamin", "EMIN & JONY")
    index.clear_history()
    assert index.history() == []
    assert NameIndex(path).history() == []


def test_past_the_cap_the_least_played_goes_first(path):
    clock = iter(range(100)).__next__
    index = NameIndex(path, clock=clock, max_history=2)
    index.add_played("Played often", "A")
    index.add_played("Played often", "A")
    index.add_played("Played once, long ago", "B")
    index.add_played("Played once, just now", "C")
    assert [e["title"] for e in index.history()] == [
        "Played often", "Played once, just now"]


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"history": "x"}'])
def test_an_unreadable_file_is_an_empty_history_not_a_crash(path, content):
    with open(path, "w") as f:
        f.write(content)
    index = NameIndex(path)
    assert index.history() == []
    assert index.history_enabled is True


def test_sources_stay_in_memory(path):
    index = NameIndex(path)
    index.set_source("library", [{"artist": "EMIN & JONY", "kind": "artist"}])
    assert [e["artist"] for e in index.entries()] == ["EMIN & JONY"]
    with open(path, "w") as f:
        json.dump({}, f)
    index.add_played("Time", "Pink Floyd")
    with open(path) as f:
        assert "EMIN" not in f.read()


def test_a_source_read_again_replaces_what_it_gave(path):
    index = NameIndex(path)
    index.set_source("favorites", [{"title": "Old favourite"}])
    index.set_source("favorites", [{"title": "New favourite"}])
    assert [e["title"] for e in index.entries()] == ["New favourite"]


# -- the one question: which known name sounds like what was heard -------------

def test_camin_finds_kamin(path):
    index = NameIndex(path)
    index.add_played("Kamin", "EMIN & JONY")
    index.add_played("Seguissèm lo nòstre camin", "La Mal Coiffée")
    index.add_played("Time", "Pink Floyd")
    (score, best), *rest = index.match("camin")
    assert best["title"] == "Kamin" and score == 1.0
    assert all(s < score for s, _ in rest)


def test_the_heard_artist_counts_too(path):
    index = NameIndex(path)
    index.add_played("Kamin", "EMIN & JONY")
    index.add_played("Kamin", "Someone Else Entirely")
    (_, best), _ = index.match("camin", "emin e jony")
    assert best["artist"] == "EMIN & JONY"


def test_a_library_artist_answers_a_name_said_alone(path):
    index = NameIndex(path)
    index.set_source("library", [{"artist": "EMIN & JONY", "kind": "artist"}])
    (score, best), = index.match("emin e jony")
    assert best["artist"] == "EMIN & JONY" and score > 0.8


def test_a_tie_goes_to_the_more_played(path):
    index = NameIndex(path)
    index.add_played("Kamin", "A")
    for _ in range(3):
        index.add_played("Kamin", "B")
    (_, first), (_, second) = index.match("kamin")
    assert (first["artist"], second["artist"]) == ("B", "A")


def test_nothing_heard_matches_nothing(path):
    index = NameIndex(path)
    index.add_played("Kamin", "EMIN & JONY")
    assert index.match("", None) == []


# -- the feature: licence, the player's reading, the sources -------------------

class _License:
    def __init__(self, pro=True):
        self.pro = pro

    def is_pro(self):
        return self.pro


class _Player:
    """The music system as the feature sees it."""

    def __init__(self, now=None, favorites=(), artists=(), fail=()):
        self.now = now
        self.favorites = list(favorites)
        self.artists = list(artists)
        self.fail = set(fail)
        self.asked = []

    def now_playing_info(self):
        self.asked.append("now")
        if "now" in self.fail:
            raise OSError("not answering")
        return self.now

    def favorites_items(self, count=50):
        self.asked.append("favorites")
        if "favorites" in self.fail:
            raise OSError("not answering")
        return self.favorites

    def local_artists(self, count=500):
        self.asked.append("artists")
        if "artists" in self.fail:
            raise OSError("not answering")
        return self.artists


def _names(path, *, pro=True, caps=None, clock=lambda: 0.0):
    return Names(NameIndex(path), _License(pro), capabilities=caps,
                 spawn=lambda fn, *a: fn(*a), sleep=lambda s: None, clock=clock)


def test_a_play_is_recorded_as_the_player_spells_it(path):
    names = _names(path)
    player = _Player(now={"title": "Kamin", "artist": "EMIN & JONY"})
    names.note_played(player, ["Kamin"])
    assert [(e["title"], e["artist"]) for e in names.index.history()] == [
        ("Kamin", "EMIN & JONY")]


def test_a_reading_about_another_track_is_not_recorded(path):
    """The player a beat behind, still on the previous song."""
    names = _names(path)
    names.note_played(_Player(now={"title": "Time", "artist": "Pink Floyd"}),
                      ["Kamin"])
    assert names.index.history() == []


@pytest.mark.parametrize("now", [None, {}])
def test_nothing_playing_is_not_recorded(path, now):
    names = _names(path)
    names.note_played(_Player(now=now), ["Kamin"])
    assert names.index.history() == []


def test_a_player_that_does_not_answer_costs_nothing(path):
    names = _names(path)
    names.note_played(_Player(fail={"now"}), ["Kamin"])
    assert names.index.history() == []


def test_without_pro_nothing_is_asked_or_kept(path):
    names = _names(path, pro=False)
    player = _Player(now={"title": "Kamin", "artist": "EMIN & JONY"})
    names.note_played(player, ["Kamin"])
    assert player.asked == []
    assert names.index.history() == []


def test_history_off_asks_the_player_nothing_about_the_play(path):
    names = _names(path)
    names.index.set_history_enabled(False)
    player = _Player(now={"title": "Kamin", "artist": "EMIN & JONY"})
    names.note_played(player, ["Kamin"])
    assert "now" not in player.asked
    assert names.index.history() == []


@pytest.mark.parametrize("terms, title, artist, vouched", [
    (["Kamin"], "Kamin", "EMIN & JONY", True),
    (["Kamin"], "Kamin (Remix)", "EMIN & JONY", True),
    (["EMIN"], "Kamin", "EMIN & JONY", True),            # an artist play
    (["Kamin", "EMIN & JONY"], "Kamin", "EMIN & JONY", True),
    (["Time"], "Timeless", "Someone", False),              # words, not letters
    (["Kamin"], "Time", "Pink Floyd", False),
    ([], "Kamin", "EMIN & JONY", False),
])
def test_what_counts_as_the_same_play(terms, title, artist, vouched):
    assert _vouched_for(terms, title, artist) is vouched


def test_sources_are_read_once_then_after_the_interval(path):
    t = [0.0]
    names = _names(path, clock=lambda: t[0])
    player = _Player(now={"title": "Kamin", "artist": "X"},
                     favorites=[{"name": "Radio Paradise"}],
                     artists=[{"title": "EMIN & JONY"}])
    names.note_played(player, ["Kamin"])
    names.note_played(player, ["Kamin"])
    assert player.asked.count("artists") == 1
    t[0] = 7 * 3600
    names.note_played(player, ["Kamin"])
    assert player.asked.count("artists") == 2
    known = {e.get("title") or e.get("artist") for e in names.index.entries()}
    assert {"Radio Paradise", "EMIN & JONY", "Kamin"} <= known


def test_only_the_sources_the_backend_declares_are_read(path):
    names = _names(path, caps=Capabilities(local_library=True))
    player = _Player(artists=[{"title": "EMIN & JONY"}])
    names.refresh(player)
    assert player.asked == ["artists"]


def test_a_source_that_fails_keeps_what_it_had(path):
    names = _names(path)
    names.refresh(_Player(artists=[{"title": "EMIN & JONY"}]))
    names.refresh(_Player(fail={"artists", "favorites"}))
    assert [e["artist"] for e in names.index.entries()] == ["EMIN & JONY"]


# -- the router: a turn that played says so, and only that ---------------------

class _Spy:
    def __init__(self):
        self.played = []

    def note_played(self, client, terms):
        self.played.append(list(terms))


def test_a_turn_that_played_reports_what(live_server, transport):
    spy = _Spy()
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]}
    live_server(names=spy).json_post("/api/v1/command",
                                     {"text": "riproduci 90125"})
    assert spy.played == [["90125"]]


def test_a_typed_turn_reports_too(live_server, transport):
    """The history is *recorded* from every turn — a typed name is spelt
    right — even though it is only ever *used* on spoken ones."""
    spy = _Spy()
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]}
    live_server(names=spy).json_post("/api/v1/command",
                                     {"text": "riproduci 90125", "via": "typed"})
    assert spy.played == [["90125"]]


@pytest.mark.parametrize("text", ["pausa", "alza il volume", "blablabla"])
def test_a_turn_that_played_nothing_says_nothing(live_server, text):
    spy = _Spy()
    live_server(names=spy).json_post("/api/v1/command", {"text": text})
    assert spy.played == []


def test_a_failing_history_never_fails_the_turn(live_server, transport):
    class _Broken:
        def note_played(self, client, terms):
            raise RuntimeError("boom")

    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]}
    reply = live_server(names=_Broken()).json_post(
        "/api/v1/command", {"text": "riproduci 90125"})
    assert reply["ok"] is True


# -- the backends: every library artist, with no query --------------------------

def test_lms_lists_library_artists_without_a_search(lms, transport):
    transport.responses["artists"] = {"artists_loop": [
        {"id": 1, "artist": "EMIN & JONY"}, {"id": 2, "artist": "Mina"}]}
    assert [a["title"] for a in lms.local_artists(count=100)] == [
        "EMIN & JONY", "Mina"]
    [cmd] = [c for c in transport.commands() if "artists" in c]
    assert not any(str(p).startswith("search:") for p in cmd)


def test_a_room_turn_reports_the_room_it_played_in(lms):
    """«metti X in cucina» plays on another player, and the aim is put back
    when the turn ends. The history must ask the kitchen what it is playing,
    not the default player, which is still on whatever it was doing."""
    from router import Router

    r = Router(lms)
    with r._aimed_at("11:22:33:44:55:66"):
        pass
    assert r.lms.player_id == lms.player_id           # the aim is put back...
    assert r._aim.last.player_id == "11:22:33:44:55:66"  # ...and remembered
