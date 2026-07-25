"""Tests for 'more like this' (P6): the streaming service's Artist Mix/radio
node for the now-playing artist, with a top-tracks fallback."""

import pytest

from router import Router


@pytest.fixture
def router(lms):
    return Router(lms)


def _now_playing(transport, artist="Pink Floyd"):
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Time", "artist": artist}]
    }


@pytest.mark.parametrize("phrase, lang", [
    ("metti qualcosa di simile", "it"),
    ("qualcosa di simile", "it"),
    ("musica simile", "it"),
    ("play something like this", "en"),
    ("more like this", "en"),
])
def test_similar_plays_artist_mix(router, transport, make_tidal, phrase, lang):
    _now_playing(transport)
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "A"},
        items={
            "A": [{"id": "AR", "name": "Pink Floyd"}],
            "AR": [{"name": "Top Tracks", "id": "TT"},
                   {"name": "Artist Mix", "id": "MIX"}],
        },
    )
    res = router.handle(phrase, lang=lang)
    assert res.ok is True
    assert "Pink Floyd" in res
    assert ["tidal", "playlist", "play", "item_id:MIX"] in transport.commands()


def test_similar_falls_back_to_top_tracks(router, transport, make_tidal):
    _now_playing(transport)
    transport.responses["tidal"] = make_tidal(
        categories={"Artists": "A"},
        items={
            "A": [{"id": "AR", "name": "Pink Floyd"}],
            "AR": [{"name": "Top Tracks", "id": "TT"}],
            "TT": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Time"},
                   {"isaudio": 1, "url": "tidal://2.flc", "name": "Money"}],
        },
    )
    res = router.handle("metti qualcosa di simile")
    assert res.ok is True
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()
    assert ["playlist", "add", "tidal://2.flc"] in transport.commands()


def test_similar_with_nothing_playing(router, transport):
    transport.responses["status"] = {"playlist_loop": []}
    res = router.handle("metti qualcosa di simile")
    assert res.ok is False
    assert res == "Non sta suonando niente: metti prima una canzone."
