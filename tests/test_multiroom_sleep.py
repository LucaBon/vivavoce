"""Multi-room targeting (Pro, ``localvoice/pro/multiroom.py``), sleep timer,
and mini-player volume.

Engine (AGPL): ``for_player`` / ``volume_set`` / ``sleep`` / volume in
``status_info`` — mechanisms only. The multi-room *feature* (room-phrase
extraction, fuzzy player matching, license gate) lives in the proprietary
``pro/multiroom.py`` and reaches the AGPL router/server as an injected object,
exactly like kid-safe.
Server: ``/players``, per-player ``/command`` · ``/player`` · ``/nowplaying``,
the mini-player ``volume`` action, and the Pro gate on all of it.
"""

import pytest

from conftest import FakeLicense
from messages import msg
from pro.multiroom import MultiRoom
from router import Router


PLAYERS = [
    {"playerid": "aa:aa", "name": "Salotto"},
    {"playerid": "bb:bb", "name": "Cucina"},
]


# -- engine: per-player client, volume, sleep ---------------------------------

def test_for_player_returns_retargeted_clone(lms):
    clone = lms.for_player("11:22:33:44:55:66")
    assert clone is not lms
    assert clone.player_id == "11:22:33:44:55:66"
    assert clone.base_url == lms.base_url
    assert lms.player_id == "aa:bb:cc:dd:ee:ff"  # the original is untouched


def test_for_player_same_or_empty_returns_self(lms):
    assert lms.for_player("aa:bb:cc:dd:ee:ff") is lms
    assert lms.for_player("") is lms
    assert lms.for_player(None) is lms


def test_for_player_commands_reach_that_player(lms, transport):
    lms.for_player("11:22").pause()
    assert transport.last_call() == ("11:22", ["pause", "1"])


def test_volume_set_clamps_to_0_100(lms, transport):
    lms.volume_set(140)
    assert transport.last_call()[1] == ["mixer", "volume", "100"]
    lms.volume_set(-3)
    assert transport.last_call()[1] == ["mixer", "volume", "0"]


def test_sleep_command_and_cancel(lms, transport):
    lms.sleep(1800)
    assert transport.last_call()[1] == ["sleep", "1800"]
    lms.sleep(0)
    assert transport.last_call()[1] == ["sleep", "0"]


def test_status_info_carries_volume(lms, transport):
    transport.responses["status"] = {
        "mode": "play", "mixer volume": 40,
        "playlist_loop": [{"title": "Time"}],
    }
    assert lms.status_info()["volume"] == 40


def test_status_info_muted_negative_volume_reads_zero(lms, transport):
    transport.responses["status"] = {
        "mode": "play", "mixer volume": -40,
        "playlist_loop": [{"title": "Time"}],
    }
    assert lms.status_info()["volume"] == 0


def test_status_info_missing_volume_is_none(lms, transport):
    transport.responses["status"] = {"mode": "stop"}
    assert lms.status_info()["volume"] is None


# -- router: sleep timer ------------------------------------------------------

@pytest.fixture
def router(lms):
    return Router(lms)


@pytest.mark.parametrize(
    "phrase, seconds",
    [
        ("spegni tra 30 minuti", "1800"),
        ("spegniti fra 10 minuti", "600"),
        ("stop tra trenta minuti", "1800"),
        ("spegni tra mezz'ora", "1800"),
        ("ferma la musica tra un'ora", "3600"),
    ],
)
def test_sleep_phrases_it(router, transport, phrase, seconds):
    router.handle(phrase)
    assert transport.last_call()[1] == ["sleep", seconds]


@pytest.mark.parametrize(
    "phrase, seconds",
    [
        ("stop in 30 minutes", "1800"),
        ("sleep in half an hour", "1800"),
        ("turn off in an hour", "3600"),
        ("switch off in twenty minutes", "1200"),
    ],
)
def test_sleep_phrases_en(router, transport, phrase, seconds):
    router.handle(phrase, lang="en")
    assert transport.last_call()[1] == ["sleep", seconds]


def test_sleep_reply_says_minutes(router, transport):
    assert router.handle("spegni tra 30 minuti") == "Va bene, spengo tra 30 minuti."


def test_sleep_cancel_it(router, transport):
    assert router.handle("annulla il timer") == "Timer di spegnimento annullato."
    assert transport.last_call()[1] == ["sleep", "0"]


def test_sleep_cancel_en(router, transport):
    assert router.handle("cancel the sleep timer", lang="en") == "Sleep timer cancelled."
    assert transport.last_call()[1] == ["sleep", "0"]


def test_stop_without_duration_still_pauses(router, transport):
    router.handle("stop")
    assert transport.last_call()[1] == ["pause", "1"]


def test_play_title_with_duration_is_not_a_sleep(router, transport, make_tidal):
    # A play command stays a play even when it ends like a duration.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc",
                      "name": "Meet Me in 10 Minutes"}]},
    )
    router.handle("play Meet Me in 10 minutes", lang="en", source="tidal")
    assert ["sleep", "600"] not in transport.commands()


# -- pro/multiroom: room targeting («in cucina») ------------------------------

def make_multiroom(pro=True, players=PLAYERS):
    """A MultiRoom over a static player list; pro=None means no license
    infrastructure at all (always gated)."""
    return MultiRoom(FakeLicense(pro) if pro is not None else None,
                     lambda: players)


@pytest.fixture
def room_router(lms):
    return Router(lms, multiroom=make_multiroom(pro=True))


def test_room_suffix_targets_that_player(room_router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://42.flc", "name": "Time"}]},
    )
    reply = room_router.handle("metti Time in cucina", source="tidal")
    assert str(reply) == "Riproduco Time da TIDAL in Cucina."
    assert ("bb:bb", ["playlist", "play", "tidal://42.flc"]) in transport.calls


def test_room_prefix_targets_that_player(room_router, transport, make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://42.flc", "name": "Time"}]},
    )
    room_router.handle("in cucina metti Time", source="tidal")
    assert ("bb:bb", ["playlist", "play", "tidal://42.flc"]) in transport.calls


def test_room_transport_command(room_router, transport):
    reply = room_router.handle("pausa in salotto")
    assert ("aa:aa", ["pause", "1"]) in transport.calls
    assert str(reply) == "In pausa in Salotto."


def test_room_english_with_article(lms, transport):
    kitchen = Router(lms, multiroom=make_multiroom(
        players=[{"playerid": "kk:kk", "name": "Kitchen"},
                 {"playerid": "ll:ll", "name": "Living Room"}]))
    kitchen.handle("pause in the kitchen", lang="en")
    assert ("kk:kk", ["pause", "1"]) in transport.calls


def test_title_containing_in_is_not_hijacked(room_router, transport, make_tidal):
    # "America" names no player: the phrase stays a title on the default player.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc",
                      "name": "Breakfast in America"}]},
    )
    room_router.handle("metti Breakfast in America", source="tidal")
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()
    assert all(player == "aa:bb:cc:dd:ee:ff" for player, _cmd in transport.calls)


def test_room_list_then_pick_stays_in_the_room(room_router, transport):
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = {
        "albums_loop": [{"id": 10, "album": "Fragile"}, {"id": 11, "album": "90125"}]
    }
    room_router.handle("quali album ho di Yes in cucina")
    reply = room_router.handle("metti la 2")
    assert ("bb:bb", ["playlistcontrol", "cmd:load", "album_id:11"]) in transport.calls
    assert str(reply) == "Riproduco 90125 dalla tua musica in Cucina."


def test_fresh_list_without_room_forgets_the_room(room_router, transport):
    transport.responses["artists"] = {"artists_loop": [{"id": 1, "artist": "Yes"}]}
    transport.responses["albums"] = {
        "albums_loop": [{"id": 10, "album": "Fragile"}, {"id": 11, "album": "90125"}]
    }
    room_router.handle("quali album ho di Yes in cucina")
    room_router.handle("quali album ho di Yes")  # re-opened without a room
    room_router.handle("metti la 1")
    picks = [c for c in transport.calls if c[1][:2] == ["playlistcontrol", "cmd:load"]]
    assert picks[-1][0] == "aa:bb:cc:dd:ee:ff"


def test_a_song_title_is_not_a_room(lms, transport):
    """The fuzzy path used to open at 0.75 with no length floor, so a player
    called «Amelia» claimed «metti Breakfast in America»."""
    router = Router(lms, multiroom=make_multiroom(
        players=[{"playerid": "am:am", "name": "Amelia"},
                 {"playerid": "pa:pa", "name": "Paradiso"}]))
    for phrase in ("metti Breakfast in America", "metti Lost in Paradise"):
        assert router.multiroom.extract_room(phrase, "it")[1] is None


def test_a_real_room_still_matches_through_asr_spelling(lms):
    mr = make_multiroom(players=[{"playerid": "s:s", "name": "Salotto Hi-Fi"}])
    stripped, player = mr.extract_room("metti Time in salotto", "it")
    assert player["playerid"] == "s:s"
    assert stripped == "metti Time"


def test_a_disconnected_player_is_not_a_room(lms):
    mr = make_multiroom(players=[{"playerid": "c:c", "name": "Cucina",
                                  "connected": 0}])
    assert mr.extract_room("metti Time in cucina", "it")[1] is None


def test_room_targeting_is_pro_gated(lms, transport):
    # No license infrastructure: a room-targeted command gets the Pro pitch
    # and nothing reaches the LMS.
    free = Router(lms, multiroom=make_multiroom(pro=None))
    reply = free.handle("metti Time in cucina")
    assert "Pro" in str(reply)
    assert transport.calls == []


def test_the_gated_reply_names_the_room_and_the_way_out(lms, transport):
    """The refusal has to say which room it thinks it heard.

    Not manners: a room name is a GUESS about what the words meant, and this
    sentence is the only place it becomes visible. On a system with a player
    called «America», «metti breakfast in america» is refused as a room
    command — and until this reply named the room, the listener had no way to
    see why a song they own was answered with an advertisement. (That the
    guess wins at all is the open half: T2.7.)

    It also has to offer the one-turn way out, which is what makes refusing
    cheap for whoever is talking rather than a dead end."""
    free = Router(lms, multiroom=make_multiroom(pro=None))
    reply = str(free.handle("metti Time in cucina"))
    assert "Cucina" in reply, reply
    assert "senza la stanza" in reply, reply
    # And it is NOT the shared wall that also answers kid-safe: that one
    # cannot name a room, so reusing it is what hid the guess.
    assert reply != msg("pro_required")


def test_room_targeting_gated_on_revoked_license(lms, transport):
    revoked = Router(lms, multiroom=make_multiroom(pro=False))
    reply = revoked.handle("pausa in cucina")
    assert "Pro" in str(reply)
    assert transport.calls == []


def test_no_multiroom_module_means_no_room_parsing(lms, transport, make_tidal):
    # Without the pro module injected, the router owns zero room logic: the
    # phrase is just a (failing) search, never a Pro pitch.
    transport.responses["tidal"] = make_tidal(categories={}, items={})
    plain = Router(lms)
    reply = plain.handle("metti Time in cucina", source="tidal")
    assert "Pro" not in str(reply)


# -- server: /players, per-player endpoints, volume ---------------------------

class FakeArtworkFetch:
    def __call__(self, url, timeout=5.0):
        return "image/png", b"PNGDATA"


@pytest.fixture
def http_server(live_server, lms):
    """The handler with an active Pro license (multi-room unlocked)."""
    return live_server(artwork_fetch=FakeArtworkFetch(),
                       license_mgr=FakeLicense(pro=True),
                       multiroom=MultiRoom(FakeLicense(pro=True),
                                           lms.get_players))


@pytest.fixture
def http_server_free(live_server, lms):
    """The handler with no license: multi-room must be inert."""
    return live_server(artwork_fetch=FakeArtworkFetch(), license_mgr=None,
                       multiroom=MultiRoom(None, lms.get_players))


def test_players_endpoint(http_server, transport):
    transport.responses["players"] = {"players_loop": PLAYERS}
    resp = http_server.get("/players")
    assert resp.status == 200
    assert resp.json() == {
        "ok": True, "pro": True, "current": "aa:bb:cc:dd:ee:ff",
        "players": [{"id": "aa:aa", "name": "Salotto"},
                    {"id": "bb:bb", "name": "Cucina"}],
    }


def test_players_endpoint_lms_down_is_not_500(http_server, transport):
    transport.raise_on.add("players")
    resp = http_server.get("/players")
    assert resp.status == 200
    assert resp.json() == {"ok": False, "players": []}


PLAYING = {
    "mode": "play", "time": 10, "mixer volume": 40,
    "playlist_loop": [{"title": "Time", "artist": "Pink Floyd",
                       "coverid": "ab12cd", "duration": 421}],
}


def test_nowplaying_honours_player_param(http_server, transport):
    transport.responses["status"] = PLAYING
    resp = http_server.get("/nowplaying?player=bb%3Abb")
    assert resp.status == 200
    data = resp.json()
    assert data["volume"] == 40
    # The status query ran against the requested player, and the artwork URL
    # keeps pointing the proxy at it.
    assert ("bb:bb", ["status", "-", "1", "tags:aAlKcdJ"]) in transport.calls
    assert "player=bb%3Abb" in data["artwork"]


def test_player_volume_action(http_server, transport):
    transport.responses["status"] = PLAYING
    resp = http_server.post_json(
        "/player", {"action": "volume", "value": 55, "player": "bb:bb"})
    assert resp.status == 200
    assert resp.json()["ok"] is True
    assert ("bb:bb", ["mixer", "volume", "55"]) in transport.calls


def test_command_routes_to_the_selected_player(http_server, transport):
    resp = http_server.post_json(
        "/command", {"text": "pausa", "client": "c1", "player": "bb:bb"})
    assert resp.status == 200
    assert resp.json()["speech"] == "In pausa."
    assert ("bb:bb", ["pause", "1"]) in transport.calls


# -- server: the multi-room Pro gate ------------------------------------------

def test_free_tier_player_param_is_ignored(http_server_free, transport):
    transport.responses["status"] = PLAYING
    http_server_free.post_json("/player",
                               {"action": "pause", "player": "bb:bb"})
    assert ("aa:bb:cc:dd:ee:ff", ["pause", "1"]) in transport.calls
    assert all(player != "bb:bb" for player, _cmd in transport.calls)


def test_free_tier_command_player_is_ignored(http_server_free, transport):
    http_server_free.post_json(
        "/command", {"text": "pausa", "client": "c1", "player": "bb:bb"})
    assert ("aa:bb:cc:dd:ee:ff", ["pause", "1"]) in transport.calls
    assert all(player != "bb:bb" for player, _cmd in transport.calls)


def test_free_tier_voice_room_gets_the_pro_pitch(http_server_free, transport):
    transport.responses["players"] = {"players_loop": PLAYERS}
    resp = http_server_free.post_json(
        "/command", {"text": "metti Time in cucina", "client": "c1"})
    assert resp.status == 200
    assert "Pro" in resp.json()["speech"]
    assert all(cmd[0] != "playlist" for _p, cmd in transport.calls)


def test_free_tier_players_endpoint_reports_pro_false(http_server_free, transport):
    transport.responses["players"] = {"players_loop": PLAYERS}
    data = http_server_free.json_get("/players")
    assert data["ok"] is True
    assert data["pro"] is False
