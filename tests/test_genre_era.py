"""Tests for genre and era playback on the local library (P3): "metti del
jazz" / "play some jazz" plays the library GENRE shuffled, "musica anni 80" /
"80s music" queues the decade — fully offline, something a cloud assistant
can't do on a personal collection."""

import pytest

from router import Router


@pytest.fixture
def router(lms):
    return Router(lms)


# -- genre -------------------------------------------------------------------
@pytest.mark.parametrize("phrase", ["metti del jazz", "metti un po' di jazz",
                                    "riproduci jazz"])
def test_genre_play_it(router, transport, phrase):
    transport.responses["genres"] = {"genres_loop": [{"id": 5, "genre": "Jazz"}]}
    assert router.handle(phrase, source="local") == (
        "Riproduco Jazz dalla tua musica, in ordine casuale."
    )
    assert ["playlistcontrol", "cmd:load", "genre_id:5"] in transport.commands()
    assert ["playlist", "shuffle", "1"] in transport.commands()


def test_genre_play_en(router, transport):
    transport.responses["genres"] = {"genres_loop": [{"id": 5, "genre": "Jazz"}]}
    assert router.handle("play some jazz", source="local", lang="en") == (
        "Playing Jazz from your music, on shuffle."
    )
    assert ["playlistcontrol", "cmd:load", "genre_id:5"] in transport.commands()


def test_genre_wins_in_auto_source(router, transport):
    transport.responses["genres"] = {"genres_loop": [{"id": 5, "genre": "Jazz"}]}
    router.handle("metti del jazz", source="auto")
    assert ["playlistcontrol", "cmd:load", "genre_id:5"] in transport.commands()
    assert not any(c[0] == "tidal" for c in transport.commands())


def test_no_genre_match_falls_through_to_song_search(router, transport, make_tidal):
    # "metti del jazz" with no jazz genre in the library -> ordinary search.
    transport.responses["genres"] = {"count": 0}
    for name in ("albums", "artists", "titles"):
        transport.responses[name] = {"count": 0}
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Jazz"}]},
    )
    assert router.handle("metti del jazz", source="auto") == "Riproduco Jazz da TIDAL."


def test_real_title_not_stolen_by_genre(router, transport, make_tidal):
    # A loose genre row must not hijack a title query ("Rock DJ" vs genre Rock
    # would score below the confidence bar -> falls through).
    transport.responses["genres"] = {"genres_loop": [{"id": 7, "genre": "Rock"}]}
    for name in ("albums", "artists", "titles"):
        transport.responses[name] = {"count": 0}
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://2.flc", "name": "Rock DJ"}]},
    )
    assert router.handle("metti Rock DJ", source="auto") == "Riproduco Rock DJ da TIDAL."
    assert not any(str(p).startswith("genre_id:")
                   for c in transport.commands() for p in c)


# -- era / decade -------------------------------------------------------------
def _years(transport):
    transport.responses["years"] = {
        "years_loop": [{"year": 1979}, {"year": 1982}, {"year": 1985},
                       {"year": 1991}]
    }


@pytest.mark.parametrize("phrase", ["metti musica anni 80",
                                    "musica degli anni ottanta",
                                    "metti gli anni 80"])
def test_decade_play_it(router, transport, phrase):
    _years(transport)
    assert router.handle(phrase, source="local") == (
        "Riproduco la musica degli anni 80 dalla tua musica, "
        "in ordine casuale."
    )
    cmds = transport.commands()
    assert ["playlistcontrol", "cmd:load", "year:1982"] in cmds
    assert ["playlistcontrol", "cmd:add", "year:1985"] in cmds
    assert ["playlist", "shuffle", "1"] in cmds
    # years outside the decade are not queued
    assert not any("year:1979" in c or "year:1991" in c for c in cmds)


@pytest.mark.parametrize("phrase", ["play 80s music", "music from the 80s",
                                    "eighties music"])
def test_decade_play_en(router, transport, phrase):
    _years(transport)
    assert router.handle(phrase, source="local", lang="en") == (
        "Playing 80s music from your library, on shuffle."
    )
    assert ["playlistcontrol", "cmd:load", "year:1982"] in transport.commands()


def test_decade_without_matching_years_is_honest(router, transport):
    transport.responses["years"] = {"years_loop": [{"year": 2001}]}
    res = router.handle("metti musica anni 60", source="local")
    assert res == "Non ho musica degli anni 60 nella tua libreria."
    assert not any(c[0] == "playlistcontrol" for c in transport.commands())


def test_non_decade_word_falls_through(router, transport, make_tidal):
    # "play beatles music" ends in s but is not a decade -> normal search.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://3.flc",
                      "name": "Beatles Music"}]},
    )
    router.handle("play beatles music", source="tidal", lang="en")
    assert ["playlist", "play", "tidal://3.flc"] in transport.commands()
