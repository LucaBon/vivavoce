"""Tests for the disambiguation choice memory (P5): a 'did you mean' answered
once is remembered — the next identical ambiguous query plays the remembered
pick straight away, transparently (one local JSON file)."""

import pytest

from prefs_store import PrefsStore
from router import Router


@pytest.fixture
def prefs(tmp_path):
    return PrefsStore(str(tmp_path / "choices.json"))


def _brick_feed(transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc",
             "name": "Another Brick in the Wall, Pt. 1"},
            {"isaudio": 1, "url": "tidal://2.flc",
             "name": "Another Brick in the Wall, Pt. 2"},
        ]},
    )


# -- store -------------------------------------------------------------------
def test_store_roundtrip(prefs):
    assert prefs.get("brick") is None
    prefs.put("Brick", "Another Brick in the Wall, Pt. 2")
    assert prefs.get("brick") == "Another Brick in the Wall, Pt. 2"
    assert prefs.get("BRICK ") == "Another Brick in the Wall, Pt. 2"


def test_store_survives_missing_file(tmp_path):
    store = PrefsStore(str(tmp_path / "does-not-exist.json"))
    assert store.get("anything") is None


# -- router integration -------------------------------------------------------
def test_pick_is_recorded_then_recalled(lms, transport, make_tidal, prefs):
    _brick_feed(transport, make_tidal)
    router = Router(lms, prefs=prefs)
    ask = router.handle("metti brick", source="tidal")
    assert getattr(ask, "kind", None) == "disambiguate"
    picked = router.handle("la 2")
    assert picked.startswith("Riproduco Another Brick in the Wall, Pt. 2")
    assert prefs.get("brick") == "Another Brick in the Wall, Pt. 2"

    # A fresh router (server restart) with the same store: no ask this time.
    router2 = Router(lms, prefs=prefs)
    res = router2.handle("metti brick", source="tidal")
    assert getattr(res, "kind", None) != "disambiguate"
    assert res.startswith("Riproduco Another Brick in the Wall, Pt. 2")
    assert transport.commands().count(["playlist", "play", "tidal://2.flc"]) == 2


def test_recalled_choice_can_be_overridden(lms, transport, make_tidal, prefs):
    prefs.put("brick", "Another Brick in the Wall, Pt. 2")
    _brick_feed(transport, make_tidal)
    router = Router(lms, prefs=prefs)
    res = router.handle("metti brick", source="tidal")
    assert getattr(res, "kind", None) != "disambiguate"
    # The candidates stay stored: an immediate correction still works and
    # re-records the new preference.
    assert router.handle("metti la 1").startswith(
        "Riproduco Another Brick in the Wall, Pt. 1")
    assert prefs.get("brick") == "Another Brick in the Wall, Pt. 1"


def test_stale_memory_falls_back_to_asking(lms, transport, make_tidal, prefs):
    prefs.put("brick", "A Song That No Longer Matches")
    _brick_feed(transport, make_tidal)
    router = Router(lms, prefs=prefs)
    res = router.handle("metti brick", source="tidal")
    assert getattr(res, "kind", None) == "disambiguate"


def test_no_prefs_keeps_asking(lms, transport, make_tidal):
    # Without a store there is no memory: a fresh router (new session) asks
    # the same ambiguous query again.
    _brick_feed(transport, make_tidal)
    for _ in range(2):
        res = Router(lms).handle("metti brick", source="tidal")
        assert getattr(res, "kind", None) == "disambiguate"


def test_plain_list_pick_is_not_recorded(lms, transport, prefs):
    # Picks from ordinary lists ("quali album ho di X") are navigation, not
    # disambiguation answers: nothing must be remembered for them.
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125"}, {"id": 9, "album": "Fragile"}]
    }
    router = Router(lms, prefs=prefs)
    router.handle("quali album ho di Yes")
    router.handle("metti la 2")
    assert prefs.get("Yes") is None
    assert prefs.get("quali album ho di Yes") is None
