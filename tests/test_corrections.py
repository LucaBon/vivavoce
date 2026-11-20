"""Corrections the household confirmed (phase 2 of
docs/name-recognition-design.md): offered under a written answer that
corrected a spoken one, kept only on a tap, applied before a spoken turn is
routed.

The case that needs it: «metti Kamin di EMIN e JONY», said, arrives as «metti
coming di eminem e johnny» — and *plays something*, by Eminem. Nothing after
the fact may overrule a turn that played; only the person who asked can say
it was wrong. They do it by writing what they meant.
"""

import pytest

from conftest import FakeLicense
from pro.corrections import Corrections
from pro.name_index import NameIndex
from pro.names import Names
from router import Router

HEARD = "metti coming di eminem e johnny"
MEANT = "metti Kamin di EMIN & JONY"
# A title that holds every word heard, so the search plays it outright — the
# point of the case: the misheard turn is a turn that PLAYED.
EMINEM = {"id": 4, "title": "Coming di Eminem e Johnny (Live)", "artist": "Eminem"}
KAMIN = {"id": 9, "title": "Kamin", "artist": "EMIN & JONY"}


# -- the store -------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return Corrections(str(tmp_path / "corrections.json"))


def test_a_correction_is_found_by_its_letters(store):
    store.add("coming di eminem e johnny", "Kamin di EMIN & JONY")
    assert store.lookup("Coming di Eminem e Johnny")["meant"] == "Kamin di EMIN & JONY"


def test_or_by_an_identical_sound(store):
    store.add("coming di eminem e johnny", "Kamin di EMIN & JONY")
    assert store.lookup("comming di eminem e jony") is not None


def test_but_not_by_a_merely_similar_one(store):
    """A confirmed rule is precise: «coming» is not «come in»."""
    store.add("coming", "Kamin")
    assert store.lookup("come in") is None
    assert store.lookup("camin") is None


def test_each_language_has_its_own(store):
    store.add("coming", "Kamin", "it")
    assert store.lookup("coming", "en") is None


def test_the_latest_confirmation_wins(store):
    store.add("coming", "Kamin")
    store.add("coming", "Kamin (Remix)")
    assert [c["meant"] for c in store.items()] == ["Kamin (Remix)"]


@pytest.mark.parametrize("heard, meant", [("", "x"), ("x", ""), ("Kamin", "kamin")])
def test_nothing_to_correct_is_not_kept(store, heard, meant):
    assert store.add(heard, meant) is None
    assert store.items() == []


def test_forgetting_one(store):
    item = store.add("coming", "Kamin")
    assert store.forget(item["id"])
    assert not store.forget(item["id"])
    assert store.lookup("coming") is None


def test_they_survive_a_restart(store, tmp_path):
    store.add("coming", "Kamin")
    assert Corrections(str(tmp_path / "corrections.json")).lookup("coming")


def test_past_the_cap_the_least_recently_used_goes(tmp_path):
    t = iter(range(100)).__next__
    store = Corrections(str(tmp_path / "c.json"), clock=t, max_items=2)
    store.add("one", "Uno")
    store.add("two", "Due")
    store.lookup("one")         # used: now the most recent
    store.add("three", "Tre")
    assert {c["heard"] for c in store.items()} == {"one", "three"}


# -- the router: offer, keep, apply ------------------------------------------------

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def catalog(transport):
    """The local library: Eminem answers what was heard, Kamin what was meant."""
    def titles(cmd):
        term = next((p[7:] for p in cmd if str(p).startswith("search:")), "").lower()
        return {"titles_loop": {"coming di eminem e johnny": [EMINEM],
                                "kamin di emin & jony": [KAMIN]}.get(term, [])}
    transport.responses["titles"] = titles
    transport.responses["albums"] = {"albums_loop": []}
    transport.responses["artists"] = {"artists_loop": []}
    return transport


def _feature(tmp_path, pro=True):
    return Names(NameIndex(str(tmp_path / "n.json")), FakeLicense(pro=pro),
                 corrections=Corrections(str(tmp_path / "c.json")),
                 spawn=lambda fn, *a: None)


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def router(lms, catalog, tmp_path, clock):
    return Router(lms, names=_feature(tmp_path), now=clock)


def _played(transport):
    return [p for cmd in transport.commands() if cmd[:1] == ["playlistcontrol"]
            for p in cmd if str(p).startswith("track_id:")]


def _turn(router, text, via, **kw):
    return router.handle_many([text], "local", "it", via=via, **kw)


def test_the_written_correction_is_offered(router, catalog):
    _turn(router, HEARD, "voice")
    assert _played(catalog) == ["track_id:4"]     # Eminem: a turn that played
    reply = _turn(router, MEANT, "typed")
    assert reply["remember"] == {"heard": "coming di eminem e johnny",
                                 "meant": "Kamin di EMIN & JONY", "lang": "it"}


def test_it_is_offered_once(router):
    _turn(router, HEARD, "voice")
    _turn(router, MEANT, "typed")
    assert "remember" not in _turn(router, MEANT, "typed")


def test_too_late_is_not_a_correction(router, clock):
    _turn(router, HEARD, "voice")
    clock.t += 91
    assert "remember" not in _turn(router, MEANT, "typed")


def test_a_different_request_is_not_a_correction(router, catalog):
    """«vasco», then «i Queen»: somebody changed their mind."""
    _turn(router, "metti vasco", "voice")
    catalog.responses["titles"] = {"titles_loop": [{"id": 7, "title": "Queen",
                                                    "artist": "Queen"}]}
    assert "remember" not in _turn(router, "metti i Queen", "typed")


def test_a_written_turn_that_played_nothing_offers_nothing(router):
    _turn(router, HEARD, "voice")
    assert "remember" not in _turn(router, "metti Kamin di nessuno", "typed")


def test_what_the_page_heard_before_the_edit_counts_too(router):
    """Auto-send off: the transcript sat in the box, was corrected there,
    and never reached the server on its own. The page sends it along."""
    reply = _turn(router, MEANT, "typed", heard=[HEARD])
    assert reply["remember"]["heard"] == "coming di eminem e johnny"


def test_a_spoken_turn_is_never_offered(router):
    _turn(router, HEARD, "voice")
    assert "remember" not in _turn(router, MEANT, "voice")


def test_without_pro_nothing_is_offered(lms, catalog, tmp_path, clock):
    router = Router(lms, names=_feature(tmp_path, pro=False), now=clock)
    _turn(router, HEARD, "voice")
    assert "remember" not in _turn(router, MEANT, "typed")


def test_once_kept_it_is_applied_before_the_search(router, catalog):
    """The same words spoken again play what was meant — not Eminem, which
    the search would still play, and said so."""
    router.names.act({"action": "remember", "heard": "coming di eminem e johnny",
                      "meant": "Kamin di EMIN & JONY", "lang": "it"})
    reply = _turn(router, HEARD, "voice")
    assert reply["ok"] is True
    assert reply["speech"].startswith("Ho sentito «coming di eminem e johnny». ")
    assert _played(catalog) == ["track_id:9"]


def test_a_kept_correction_does_not_touch_written_turns(router, catalog):
    router.names.act({"action": "remember", "heard": "coming di eminem e johnny",
                      "meant": "Kamin di EMIN & JONY", "lang": "it"})
    _turn(router, HEARD, "typed")
    assert _played(catalog) == ["track_id:4"]


def test_a_correction_to_something_gone_falls_back_to_the_search(router, catalog):
    router.names.act({"action": "remember", "heard": "coming di eminem e johnny",
                      "meant": "Something No Longer Here", "lang": "it"})
    reply = _turn(router, HEARD, "voice")
    assert not reply["speech"].startswith("Ho sentito")
    assert _played(catalog) == ["track_id:4"]


# -- the settings section: GET and POST /names -------------------------------------

def test_without_the_feature_the_section_is_unavailable(live_server):
    srv = live_server()
    assert srv.json_get("/names") == {"pro": False, "available": False}
    assert srv.json_post("/names", {"action": "clear_history"})["ok"] is False


def test_the_section_shows_and_changes_the_state(live_server, tmp_path):
    names = _feature(tmp_path)
    names.index.add_played("Kamin", "EMIN & JONY")
    srv = live_server(names=names)
    state = srv.json_get("/names")
    assert state["available"] and state["pro"] and state["history_enabled"]
    assert state["history_count"] == 1

    state = srv.json_post("/names", {"action": "history", "enabled": False})
    assert state["ok"] and state["history_enabled"] is False
    state = srv.json_post("/names", {"action": "clear_history"})
    assert state["history_count"] == 0

    state = srv.json_post("/names", {"action": "remember", "heard": "coming",
                                     "meant": "Kamin", "lang": "it"})
    [c] = state["corrections"]
    assert (c["heard"], c["meant"]) == ("coming", "Kamin")
    state = srv.json_post("/names", {"action": "forget", "id": c["id"]})
    assert state["corrections"] == []


def test_switching_the_history_on_needs_a_literal_true(live_server, tmp_path):
    names = _feature(tmp_path)
    srv = live_server(names=names)
    srv.json_post("/names", {"action": "history", "enabled": False})
    state = srv.json_post("/names", {"action": "history", "enabled": "yes"})
    assert state["history_enabled"] is False


def test_without_pro_nothing_changes(live_server, tmp_path):
    srv = live_server(names=_feature(tmp_path, pro=False))
    state = srv.json_post("/names", {"action": "remember", "heard": "coming",
                                     "meant": "Kamin"})
    assert state["ok"] is False and state["error"] == "pro_required"
    assert state["corrections"] == []


@pytest.mark.parametrize("body", [
    {"action": "remember", "heard": ["coming"], "meant": "Kamin"},
    {"action": "remember", "heard": "coming", "meant": None},
    {"action": "nonsense"},
    {},
])
def test_a_malformed_change_is_refused_not_crashed(live_server, tmp_path, body):
    state = live_server(names=_feature(tmp_path)).json_post("/names", body)
    assert state["ok"] is False
    assert state["corrections"] == []


def test_the_command_api_carries_the_offer(live_server, catalog, tmp_path):
    srv = live_server(names=_feature(tmp_path))
    body = {"client": "phone", "source": "local"}
    srv.json_post("/api/v1/command", dict(body, text=HEARD, via="voice"))
    reply = srv.json_post("/api/v1/command", dict(body, text=MEANT, via="typed"))
    assert reply["remember"]["meant"] == "Kamin di EMIN & JONY"
