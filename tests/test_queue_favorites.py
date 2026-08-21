"""Queue management (T2.1) and favorites/radio (T2.2): the engine layer.

``play_song``/``play_local``/``choose_from``/``choose_by_name`` now take a
``mode`` ('play' | 'add' | 'insert'); 'play' is the default and every
existing test keeps passing untouched (see test_actions.py). These tests
cover the new modes plus the standalone queue/favorites/radio actions.
"""

import actions
from actions import BLOCKED_SPEECH


def _restricted(blocklist):
    return actions.Guard(restricted=True, blocklist=blocklist)


# -- play_song(mode="add"/"insert") ----------------------------------------

def test_queue_add_song(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://42.flc", "name": "Time"}]},
    )
    result = actions.play_song(lms, "time", mode="add")
    assert result == "Ho aggiunto Time alla coda."
    assert ["playlist", "add", "tidal://42.flc"] in transport.commands()
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_queue_insert_song(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://42.flc", "name": "Time"}]},
    )
    result = actions.play_song(lms, "time", mode="insert")
    assert result == "Metto Time subito dopo questa."
    assert ["playlist", "insert", "tidal://42.flc"] in transport.commands()


def test_queue_add_song_with_artist_names_it(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Money",
                      "artist": "Pink Floyd"}]},
    )
    result = actions.play_song(lms, "Money dei Pink Floyd", mode="add")
    assert result == "Ho aggiunto Money di Pink Floyd alla coda."


def test_queue_add_missing_title_never_touches_lms(lms, transport):
    assert actions.play_song(lms, "", mode="add") == "Non ho capito il titolo. Puoi ripetere?"
    assert transport.calls == []


def test_queue_add_no_results(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(categories={"Songs": "S"}, items={"S": []})
    result = actions.play_song(lms, "brano inesistente", mode="add")
    assert result == "Non ho trovato nessun brano per brano inesistente."
    assert result.ok is False


def test_queue_add_blocked(lms, transport):
    result = actions.play_song(lms, "canzone vietata", mode="add",
                               guard=_restricted(["canzone vietata"]))
    assert result == BLOCKED_SPEECH
    assert transport.calls == []


def test_queue_add_disambiguates_like_play(lms, transport, make_tidal):
    # Same "did you mean" machinery as mode="play": several strong, distinct
    # matches -> a question, no track queued yet.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [
            {"isaudio": 1, "url": "tidal://1.flc",
             "name": "Another Brick in the Wall, Pt. 1"},
            {"isaudio": 1, "url": "tidal://2.flc",
             "name": "Another Brick in the Wall, Pt. 2"},
        ]},
    )
    result = actions.play_song(lms, "brick", mode="add")
    assert result.kind == "disambiguate"
    assert not any(c[:2] in (["playlist", "add"], ["playlist", "insert"])
                   for c in transport.commands())
    picked = actions.choose_from(lms, result.candidates, 2, mode="add")
    assert picked == "Ho aggiunto Another Brick in the Wall, Pt. 2 alla coda."
    assert ["playlist", "add", "tidal://2.flc"] in transport.commands()


# -- play_song(mode=...) from an album ("Time dall'album Dark Side") -------

def test_queue_add_track_from_album(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "AL"},
        items={
            "AL": [{"type": "playlist", "id": "9", "name": "The Wall"}],
            "9": [{"isaudio": 1, "url": "tidal://5.flc", "name": "Comfortably Numb"}],
        },
    )
    result = actions.play_song(lms, "Comfortably Numb dall'album The Wall", mode="add")
    assert result == "Ho aggiunto Comfortably Numb dall'album The Wall alla coda."
    assert ["playlist", "add", "tidal://5.flc"] in transport.commands()


def test_queue_insert_whole_album_when_title_missing(lms, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Albums": "AL"},
        items={"AL": [{"type": "playlist", "id": "9", "name": "The Wall"}]},
    )
    result = actions.play_song(lms, "dall'album The Wall", mode="insert")
    assert result == "Metto l'album The Wall subito dopo questa."
    assert ["tidal", "playlist", "insert", "item_id:9"] in transport.commands()


# -- play_local(mode="add"/"insert") ----------------------------------------

def test_queue_add_local_track(lms, transport):
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {
        "titles_loop": [{"id": 5, "title": "Wish You Were Here"}]
    }
    result = actions.play_local(lms, "wish you were here", mode="add")
    assert result == "Ho aggiunto Wish You Were Here alla coda dalla tua musica."
    assert ["playlistcontrol", "cmd:add", "track_id:5"] in transport.commands()


def test_queue_insert_local_album(lms, transport):
    transport.responses["albums"] = {
        "albums_loop": [{"id": 7, "album": "The Wall"}]
    }
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = {"count": 0}
    result = actions.play_local(lms, "the wall", mode="insert")
    assert result == "Metto l'album The Wall dalla tua musica subito dopo questa."
    assert ["playlistcontrol", "cmd:insert", "album_id:7"] in transport.commands()


# -- choose_from / choose_by_name mode ---------------------------------------

def test_choose_from_add_mode(lms, transport):
    candidates = [{"title": "Fragile", "url": "tidal://9.flc"}]
    result = actions.choose_from(lms, candidates, 1, mode="add")
    assert result == "Ho aggiunto Fragile alla coda."
    assert ["playlist", "add", "tidal://9.flc"] in transport.commands()


def test_choose_from_insert_mode(lms, transport):
    candidates = [{"title": "Fragile", "url": "tidal://9.flc"}]
    result = actions.choose_from(lms, candidates, 1, mode="insert")
    assert result == "Metto Fragile subito dopo questa."
    assert ["playlist", "insert", "tidal://9.flc"] in transport.commands()


def test_choose_by_name_add_mode(lms, transport):
    candidates = [{"title": "Fragile", "url": "tidal://9.flc"}]
    result = actions.choose_by_name(lms, candidates, "fragile", mode="add")
    assert result == "Ho aggiunto Fragile alla coda."


def test_choose_from_default_mode_is_play_unchanged(lms, transport):
    candidates = [{"title": "Fragile", "url": "tidal://9.flc"}]
    result = actions.choose_from(lms, candidates, 1)
    assert result == "Riproduco Fragile."
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


# -- queue clear / list ------------------------------------------------------

def test_clear_queue(lms, transport):
    result = actions.clear_queue(lms)
    assert result == "Coda svuotata."
    assert ["playlist", "clear"] in transport.commands()


def test_clear_queue_lms_error(lms, transport):
    transport.raise_on.add("playlist")
    assert actions.clear_queue(lms) == actions.ERR_UNREACHABLE


def test_queue_list_reads_upcoming_tracks(lms, transport):
    transport.responses["status"] = {
        "playlist_loop": [
            {"title": "Now", "artist": "X"},
            {"title": "Next", "artist": "Y"},
            {"title": "Then", "artist": "Z"},
        ]
    }
    result = actions.queue_list(lms)
    assert result == "In coda: 1: Next di Y, 2: Then di Z."


def test_queue_list_empty(lms, transport):
    transport.responses["status"] = {"playlist_loop": [{"title": "Now"}]}
    assert actions.queue_list(lms) == "La coda è vuota."


def test_queue_list_lms_error(lms, transport):
    transport.raise_on.add("status")
    assert actions.queue_list(lms) == actions.ERR_UNREACHABLE


# -- favorites ----------------------------------------------------------------

def test_play_favorites(lms, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "1", "name": "Radio Paradise"},
                            {"id": "2", "name": "Deep House"}]}
    )
    result = actions.play_favorites(lms)
    assert result == "Riproduco i preferiti."
    assert ["favorites", "playlist", "play", "item_id:1"] in transport.commands()


def test_play_favorites_empty(lms, transport):
    transport.responses["favorites"] = {"loop_loop": []}
    result = actions.play_favorites(lms)
    assert result == "Non hai preferiti salvati."
    assert result.ok is False


def test_play_favorites_blocked_terms_skipped(lms, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "1", "name": "Brano Vietato"},
                            {"id": "2", "name": "Radio Paradise"}]}
    )
    result = actions.play_favorites(lms, guard=_restricted(["brano vietato"]))
    assert result == "Riproduco i preferiti."
    assert ["favorites", "playlist", "play", "item_id:2"] in transport.commands()


def test_play_favorites_lms_error(lms, transport):
    transport.raise_on.add("favorites")
    assert actions.play_favorites(lms) == actions.ERR_UNREACHABLE


# -- radio (via favorites) -----------------------------------------------------

def test_play_radio_finds_matching_favorite(lms, transport):
    transport.responses["favorites"] = lambda cmd: (
        {} if cmd[1] == "playlist"
        else {"loop_loop": [{"id": "3", "name": "Radio Paradise"}]}
    )
    result = actions.play_radio(lms, "radio paradise")
    assert result == "Metto la radio Radio Paradise."
    assert ["favorites", "playlist", "play", "item_id:3"] in transport.commands()


def test_play_radio_not_found(lms, transport):
    transport.responses["favorites"] = {"loop_loop": []}
    result = actions.play_radio(lms, "una radio inventata")
    assert result == "Non ho trovato una radio chiamata una radio inventata tra i tuoi preferiti."
    assert result.ok is False


def test_play_radio_weak_match_is_honest_miss(lms, transport):
    transport.responses["favorites"] = {
        "loop_loop": [{"id": "1", "name": "Classical Music Hour"}]
    }
    result = actions.play_radio(lms, "jazz fm")
    assert result.ok is False
    assert transport.commands() == [["favorites", "items", "0", "50", "want_url:1",
                                     "search:jazz fm"]]


def test_play_radio_missing_name(lms, transport):
    assert actions.play_radio(lms, "") == "Quale radio?"
    assert transport.calls == []


def test_play_radio_blocked(lms, transport):
    result = actions.play_radio(lms, "vietata", guard=_restricted(["vietata"]))
    assert result == BLOCKED_SPEECH
    assert transport.calls == []


def test_play_radio_lms_error(lms, transport):
    transport.raise_on.add("favorites")
    assert actions.play_radio(lms, "jazz") == actions.ERR_UNREACHABLE
