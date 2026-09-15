"""The MusicAssistant backend, against a scripted server that is not there.

Same shape as ``test_lms.py`` and for the same reason: the wire is where a
backend is wrong, and the wire is the one thing a test can hold still. Every
command name and argument name asserted below was read off
``music-assistant/server`` rather than remembered, so a test failing here
means this client drifted — not that the assertion was a guess.

The last group is the one that matters most. It runs the ordinary engine
functions — the ones that pick a record and decide whether to ask — against
this client instead of an LMS, which is the whole claim the player layer makes.
"""

import pytest

import actions
import playback
import transport as engine_transport
from player.ma_transport import MusicAssistantError
from player.musicassistant import MusicAssistantClient


def track(uri, name, artist=None, album=None):
    """A search hit shaped the way MusicAssistant serialises one."""
    item = {"uri": uri, "item_id": uri.rsplit("/", 1)[-1], "provider": "tidal",
            "name": name, "media_type": "track"}
    if artist:
        item["artists"] = [{"name": artist, "uri": f"tidal://artist/{artist}"}]
    if album:
        item["album"] = {"name": album, "uri": f"tidal://album/{album}"}
    return item


def container(uri, name, provider="tidal"):
    return {"uri": uri, "item_id": uri.rsplit("/", 1)[-1],
            "provider": provider, "name": name}


# -- construction --------------------------------------------------------------

def test_an_address_and_a_player_are_both_required():
    with pytest.raises(ValueError):
        MusicAssistantClient(base_url="", player_id="x")
    with pytest.raises(ValueError):
        MusicAssistantClient(base_url="http://x", player_id="")


def test_a_trailing_slash_on_the_address_is_dropped(ma_transport):
    client = MusicAssistantClient("http://ma.local:8095/", "p",
                                  transport=ma_transport)
    assert client.base_url == "http://ma.local:8095"


# -- the controls that resolve nothing -----------------------------------------

@pytest.mark.parametrize("method,command", [
    ("pause", "players/cmd/pause"),
    ("resume", "players/cmd/play"),
    ("next_track", "players/cmd/next"),
    ("previous_track", "players/cmd/previous"),
])
def test_a_transport_control_names_its_player(ma, ma_transport, method, command):
    getattr(ma, method)()
    assert ma_transport.last_call() == (command, {"player_id": "ma-player-1"})


def test_volume_moves_a_notch_in_the_direction_asked(ma, ma_transport):
    # The engine asks in notches of its own; MusicAssistant has a step per
    # player set by whoever wired the amplifier up, and its step wins. What
    # must survive is the direction.
    ma.volume(5)
    assert ma_transport.last_call()[0] == "players/cmd/volume_up"
    ma.volume(-5)
    assert ma_transport.last_call()[0] == "players/cmd/volume_down"


def test_an_absolute_volume_is_clamped_to_the_scale(ma, ma_transport):
    ma.volume_set(140)
    assert ma_transport.last_call()[1]["volume_level"] == 100
    ma.volume_set(-3)
    assert ma_transport.last_call()[1]["volume_level"] == 0


def test_a_sleep_timer_is_armed_and_cancelled_by_different_commands(ma, ma_transport):
    ma.sleep(600)
    assert ma_transport.last_call() == (
        "players/sleep_timer/set", {"player_id": "ma-player-1", "seconds": 600})
    # Zero is how the engine cancels, and a timer of zero seconds would stop
    # the music instead of leaving it alone.
    ma.sleep(0)
    assert ma_transport.last_call() == (
        "players/sleep_timer/clear", {"player_id": "ma-player-1"})


def test_seeking_is_whole_seconds(ma, ma_transport):
    ma.seek(42.7)
    assert ma_transport.last_call()[1]["position"] == 42


# -- the queue -----------------------------------------------------------------

def test_the_active_queue_is_asked_for_once_and_remembered(ma, ma_transport):
    # A player synced into a group plays the group's queue; clearing its own
    # would empty a queue nobody is listening to. Asking costs a round trip,
    # so it is spent once a turn rather than once a command.
    ma_transport.responses["player_queues/get_active_queue"] = {"queue_id": "group-1"}
    ma.clear_queue()
    ma.clear_queue()
    assert ma_transport.commands().count("player_queues/get_active_queue") == 1
    assert ma_transport.last_call() == ("player_queues/clear", {"queue_id": "group-1"})


def test_a_player_on_no_group_falls_back_to_its_own_queue(ma, ma_transport):
    ma.clear_queue()
    assert ma_transport.last_call() == (
        "player_queues/clear", {"queue_id": "ma-player-1"})


def test_the_upcoming_queue_starts_after_what_is_playing(ma, ma_transport):
    ma_transport.responses["player_queues/get"] = {"current_index": 3}
    ma_transport.responses["player_queues/items"] = [
        {"name": "Next One", "media_item": {"name": "Next One",
                                            "artists": [{"name": "Someone"}]}},
    ]
    upcoming = ma.queue_upcoming(5)
    assert ma_transport.args_for("player_queues/items")["offset"] == 4
    assert upcoming == [{"title": "Next One", "artist": "Someone"}]


def test_an_empty_queue_reads_back_as_nothing(ma, ma_transport):
    assert ma.queue_upcoming(5) == []


# -- what is playing -----------------------------------------------------------

@pytest.mark.parametrize("state,mode", [
    ("playing", "play"), ("paused", "pause"), ("idle", "stop"),
    ("unknown", "stop"),
])
def test_the_playback_state_becomes_the_mode_the_engine_knows(ma, ma_transport,
                                                              state, mode):
    ma_transport.responses["player_queues/get"] = {
        "state": state,
        "current_item": {"name": "x", "media_item": {"name": "Comfortably Numb"}},
    }
    assert ma.now_playing_info()["mode"] == mode


def test_nothing_playing_is_None_rather_than_a_blank_track(ma, ma_transport):
    ma_transport.responses["player_queues/get"] = {"state": "idle"}
    assert ma.now_playing_info() is None


def test_the_title_comes_from_the_media_item_not_the_display_line(ma, ma_transport):
    # A queue item's own name can already read "Artist - Title", and a spoken
    # reply that repeats the artist inside the title has nowhere to hide it.
    ma_transport.responses["player_queues/get"] = {
        "state": "playing",
        "current_item": {
            "name": "Pink Floyd - Comfortably Numb",
            "media_item": {"name": "Comfortably Numb",
                           "artists": [{"name": "Pink Floyd"}]},
        },
    }
    info = ma.now_playing_info()
    assert info["title"] == "Comfortably Numb"
    assert info["artist"] == "Pink Floyd"


def test_a_publicly_served_cover_is_used_as_it_stands(ma, ma_transport):
    ma_transport.responses["player_queues/get"] = {
        "state": "playing",
        "current_item": {"name": "x", "media_item": {"name": "x"},
                         "image": {"path": "https://cdn.example/cover.jpg",
                                   "remotely_accessible": True}},
    }
    assert ma.status_info()["artwork"] == "https://cdn.example/cover.jpg"


def test_a_private_cover_goes_through_the_servers_image_proxy(ma, ma_transport):
    # http_api only prefixes a base URL onto a path with no scheme, so what
    # this hands back has to be absolute either way.
    ma_transport.responses["player_queues/get"] = {
        "state": "playing",
        "current_item": {"name": "x", "media_item": {"name": "x"},
                         "image": {"path": "/local/thing",
                                   "remotely_accessible": False,
                                   "proxy_id": "abc123"}},
    }
    assert ma.status_info()["artwork"] == "http://ma.local:8095/imageproxy/abc123"


def test_a_cover_that_is_neither_is_simply_absent(ma, ma_transport):
    ma_transport.responses["player_queues/get"] = {
        "state": "playing",
        "current_item": {"name": "x", "media_item": {"name": "x"},
                         "image": {"path": "/local/thing",
                                   "remotely_accessible": False}},
    }
    assert ma.status_info()["artwork"] is None


# -- starting something --------------------------------------------------------

@pytest.mark.parametrize("method,option", [
    ("play_url", "replace"), ("add_url", "add"), ("insert_url", "next"),
])
def test_the_three_queue_modes_reach_the_wire_as_themselves(ma, ma_transport,
                                                            method, option):
    getattr(ma, method)("tidal://track/1")
    command, args = ma_transport.last_call()
    assert command == "player_queues/play_media"
    assert args["media"] == "tidal://track/1"
    assert args["option"] == option


def test_several_tracks_are_enqueued_in_one_call(ma, ma_transport):
    # One call, not one per track: play_media takes a list, and enqueuing them
    # one at a time races the first one starting.
    ma.play_tracks([{"url": "tidal://track/1"}, {"url": "tidal://track/2"}])
    assert ma_transport.commands().count("player_queues/play_media") == 1
    assert ma_transport.last_call()[1]["media"] == ["tidal://track/1",
                                                    "tidal://track/2"]


def test_tracks_with_no_url_are_not_enqueued_as_nothing(ma, ma_transport):
    ma.play_tracks([{"title": "no url here"}])
    assert "player_queues/play_media" not in ma_transport.commands()


# -- searching -----------------------------------------------------------------

def test_a_search_asks_for_one_media_type_and_shapes_what_comes_back(ma, ma_transport):
    ma_transport.responses["music/search"] = {
        "tracks": [track("tidal://track/55", "Comfortably Numb", "Pink Floyd",
                         "The Wall")],
    }
    found = ma.search_tracks("comfortably numb")
    assert ma_transport.args_for("music/search")["media_types"] == ["track"]
    assert found == [{"url": "tidal://track/55", "title": "Comfortably Numb",
                      "artist": "Pink Floyd", "album": "The Wall"}]


def test_an_empty_query_is_not_sent_at_all(ma, ma_transport):
    assert ma.search_tracks("   ") == []
    assert ma_transport.calls == []


def test_an_unaimed_client_searches_everything(ma, ma_transport):
    ma_transport.responses["music/search"] = {"tracks": []}
    ma.search_tracks("x")
    # Absent rather than null: every optional argument on the server has a
    # default worth having, and spelling it null overrides it with nothing.
    assert "providers" not in ma_transport.args_for("music/search")


def test_aiming_at_a_service_restricts_the_search_to_it(ma, ma_transport):
    ma_transport.responses["music/search"] = {"tracks": []}
    ma.for_service("qobuz").search_tracks("x")
    assert ma_transport.args_for("music/search")["providers"] == ["qobuz"]


def test_a_uri_is_already_playable_so_resolving_one_is_free(ma, ma_transport):
    assert ma.track_url("tidal://track/7") == "tidal://track/7"
    assert ma_transport.calls == []


def test_album_tracks_are_fetched_by_id_and_provider(ma, ma_transport):
    ma_transport.responses["music/search"] = {
        "albums": [container("tidal://album/9", "The Wall")]}
    ma_transport.responses["music/albums/album_tracks"] = [
        track("tidal://track/1", "In the Flesh?", "Pink Floyd")]
    result = ma.album_tracks("the wall")
    args = ma_transport.args_for("music/albums/album_tracks")
    assert args == {"item_id": "9", "provider_instance_id_or_domain": "tidal"}
    assert result["album"]["title"] == "The Wall"
    assert result["tracks"][0]["url"] == "tidal://track/1"


def test_an_album_nobody_has_answers_without_a_second_round_trip(ma, ma_transport):
    ma_transport.responses["music/search"] = {"albums": []}
    assert ma.album_tracks("nothing") == {"album": None, "tracks": []}
    assert "music/albums/album_tracks" not in ma_transport.commands()


def test_an_artists_tracks_are_asked_for_with_the_candidate_handed_back(ma, ma_transport):
    ma_transport.responses["music/artists/artist_tracks"] = [
        track("tidal://track/3", "Black Hole Sun", "Soundgarden")]
    artist = {"id": "tidal://artist/4", "title": "Soundgarden",
              "item_id": "4", "provider": "tidal"}
    tracks = ma.artist_tracks(artist)
    assert ma_transport.args_for("music/artists/artist_tracks") == {
        "item_id": "4", "provider_instance_id_or_domain": "tidal"}
    assert tracks[0]["title"] == "Black Hole Sun"


# -- the local library ---------------------------------------------------------

def test_the_library_is_listed_not_searched(ma, ma_transport):
    # library_items is the command MusicAssistant means for this: it sorts by
    # name rather than by relevance and consults no streaming provider.
    ma_transport.responses["music/albums/library_items"] = [
        container("library://album/2", "Kind of Blue", provider="library")]
    found = ma.local_album_candidates("kind of blue")
    assert ma_transport.args_for("music/albums/library_items") == {
        "search": "kind of blue", "limit": 10}
    assert found[0]["id"] == "library://album/2"


def test_genres_are_addressed_by_their_library_id(ma, ma_transport):
    # The one candidate shape here whose id is not a URI: music/genres/tracks
    # wants the numeric item_id.
    ma_transport.responses["music/genres/library_items"] = [
        {"item_id": 12, "name": "Jazz", "uri": "library://genre/12"}]
    assert ma.local_genres(200) == [{"id": 12, "title": "Jazz"}]


def test_playing_a_genre_loads_its_tracks(ma, ma_transport):
    ma_transport.responses["music/genres/tracks"] = [
        track("library://track/1", "So What", "Miles Davis")]
    ma.play_local_genre(12)
    assert ma_transport.args_for("music/genres/tracks") == {"item_id": 12}
    assert ma_transport.last_call()[1]["media"] == ["library://track/1"]


def test_there_are_no_years_to_offer(ma, ma_transport):
    # Declared years=False. It answers rather than raising because the mood
    # code asks first and falls through to a streaming playlist on an empty
    # list, which is the right outcome and costs nothing.
    assert ma.local_years() == []
    assert ma_transport.calls == []


def test_nothing_in_this_library_is_blocked_by_a_logged_out_plugin(ma):
    # The LMS problem this guards against does not exist here: MusicAssistant
    # resolves a URI to a provider that can stream it at play time.
    assert ma.blocking_service({"id": "library://track/1"}, "track") is None


# -- favourites ----------------------------------------------------------------

def test_favourites_come_back_under_the_key_the_engine_reads(ma, ma_transport):
    # "name", not "title": actions.play_favorites reads that key, and it is
    # the LMS favourites shape rather than a choice made here.
    ma_transport.responses["music/radios/library_items"] = [
        {"uri": "library://radio/1", "name": "Radio Popolare"}]
    items = ma.favorites_items()
    assert {"id": "library://radio/1", "name": "Radio Popolare"} in items
    assert ma_transport.args_for("music/radios/library_items")["favorite"] is True


# -- which service -------------------------------------------------------------

def test_the_local_file_providers_are_not_offered_as_streaming_sources(ma, ma_transport):
    # They are real providers, but offering one would be offering the user
    # their own files a second time.
    ma_transport.responses["config/providers"] = [
        {"domain": "tidal", "enabled": True},
        {"domain": "filesystem_local", "enabled": True},
        {"domain": "qobuz", "enabled": False},
    ]
    assert ma.installed_services() == ["tidal"]


def test_an_unaimed_client_can_always_search(ma, ma_transport):
    # Stronger than it is on LMS: MusicAssistant searches the library even
    # with no streaming provider connected at all.
    assert ma.can_search() is True
    assert ma_transport.calls == []


def test_a_service_that_is_not_configured_cannot_search(ma, ma_transport):
    ma_transport.responses["config/providers"] = [{"domain": "tidal", "enabled": True}]
    assert ma.for_service("tidal").can_search() is True
    assert ma.for_service("qobuz").can_search() is False


def test_spotifys_ranking_is_not_evidence_here_either(ma):
    # A search that always answers makes "it came back first" a guess
    # presented as an answer. That is a fact about Spotify, not about which
    # server is asking, so it is spelled the same way as in lms.SERVICES.
    assert ma.for_service("spotify").service.trust_ranking is False
    assert ma.for_service("qobuz").service.trust_ranking is True


# -- re-aiming -----------------------------------------------------------------

def test_re_aiming_at_what_it_is_already_aimed_at_costs_nothing(ma):
    assert ma.for_player(None) is ma
    assert ma.for_player("ma-player-1") is ma
    assert ma.for_service("") is ma


def test_clones_share_what_is_true_of_the_server(ma, ma_transport):
    # The queue cache and the breaker are facts about the server, not about
    # which clone asked — the same reasoning LMSClient states for its own.
    other = ma.for_player("ma-player-2")
    assert other._queues is ma._queues
    assert other._breaker is ma._breaker
    assert other.base_url == ma.base_url


def test_a_clone_commands_the_player_it_was_aimed_at(ma, ma_transport):
    ma.for_player("ma-player-2").pause()
    assert ma_transport.last_call()[1]["player_id"] == "ma-player-2"


# -- players -------------------------------------------------------------------

def test_players_are_reported_under_the_names_the_rest_of_the_app_reads(ma, ma_transport):
    # "playerid" is the LMS spelling, and it reaches the web page, /players
    # and the multi-room matcher. Renaming it is a change to a published API.
    ma_transport.responses["players/all"] = [
        {"player_id": "ma-player-1", "name": "Salotto", "available": True}]
    assert ma.get_players() == [
        {"playerid": "ma-player-1", "name": "Salotto", "connected": True}]


# -- failure -------------------------------------------------------------------

def test_a_failure_is_the_error_the_engine_catches(ma, ma_transport):
    from player.errors import PlayerError
    ma_transport.raise_on.add("players/cmd/pause")
    with pytest.raises(PlayerError):
        ma.pause()


def test_a_dead_server_is_stopped_being_dialled(ma, ma_transport):
    # The breaker comes from the shared base, so this is really a test that
    # MusicAssistant gets it too — an off server must not cost a socket
    # timeout per command all evening.
    ma_transport.raise_on.add("players/cmd/pause")
    for _ in range(4):
        with pytest.raises(MusicAssistantError):
            ma.pause()
    before = len(ma_transport.calls)
    with pytest.raises(MusicAssistantError, match="not dialled again"):
        ma.pause()
    assert len(ma_transport.calls) == before


# -- the engine, driving something that is not an LMS --------------------------
# This is the claim the whole player layer makes. These are the ordinary
# engine functions, unchanged and unaware, acting on a MusicAssistant.

def test_the_engine_pauses_a_music_assistant(ma, ma_transport):
    result = engine_transport.pause(ma)
    assert result.ok is True
    assert ma_transport.last_call()[0] == "players/cmd/pause"


def test_the_engine_reports_a_server_that_stopped_answering(ma, ma_transport):
    ma_transport.raise_on.add("players/cmd/pause")
    result = engine_transport.pause(ma)
    assert result.ok is False


def test_the_engine_plays_the_edition_by_the_artist_that_was_named(ma, ma_transport):
    # The product's whole reason to exist, on a backend that is not an LMS:
    # two records share a title and the named artist decides, rather than the
    # search engine's own first answer.
    ma_transport.responses["music/search"] = {
        "tracks": [
            track("tidal://track/1", "Yesterday", "The Beatles"),
            track("tidal://track/2", "Yesterday", "Boyz II Men"),
        ],
    }
    result = actions.play_song(ma, "Yesterday dei Boyz II Men")
    assert result.ok is True
    assert ma_transport.last_call()[1]["media"] == "tidal://track/2"


def test_the_engine_still_refuses_rather_than_playing_the_wrong_artist(ma, ma_transport):
    ma_transport.responses["music/search"] = {
        "tracks": [track("tidal://track/1", "Yesterday", "The Beatles")]}
    result = actions.play_song(ma, "Yesterday di Vasco Rossi")
    assert result.ok is False
    assert "player_queues/play_media" not in ma_transport.commands()


def test_the_engine_plays_the_exact_title_over_a_longer_one(ma, ma_transport):
    # "Waterloo" is exactly a title here, so there is nothing to ask about:
    # the record that IS the request beats the three that merely start with it.
    ma_transport.responses["music/search"] = {
        "tracks": [
            track("tidal://track/1", "Waterloo Sunset", "The Kinks"),
            track("tidal://track/2", "Waterloo", "ABBA"),
        ],
    }
    result = actions.play_song(ma, "Waterloo")
    assert result.ok is True
    assert ma_transport.last_call()[1]["media"] == "tidal://track/2"


def test_the_engine_still_asks_which_one_when_it_cannot_tell(ma, ma_transport):
    # Nothing matches the request outright and three different records match
    # it strongly. Playing any of them would be a guess in silence, which is
    # the one thing this product promises not to do — on any backend.
    ma_transport.responses["music/search"] = {
        "tracks": [
            track("tidal://track/1", "Waterloo Sunset", "The Kinks"),
            track("tidal://track/2", "Waterloo Road", "Jason Crest"),
            track("tidal://track/3", "Waterloo Bridge", "Someone Else"),
        ],
    }
    result = actions.play_song(ma, "Waterloo")
    assert [c["title"] for c in result.candidates] == [
        "Waterloo Sunset", "Waterloo Road", "Waterloo Bridge"]
    assert "player_queues/play_media" not in ma_transport.commands()


def test_a_provider_switched_off_is_a_name_this_server_knows(ma, ma_transport):
    # The two questions are different and the difference is the point:
    # installed_services is "usable today", known_services is "a name you
    # recognise". A provider being re-authenticated this morning belongs to
    # the second and not the first — calling it a typo would refuse to start
    # the whole app over an outage.
    ma_transport.responses["config/providers"] = [
        {"domain": "tidal", "enabled": False},
        {"domain": "qobuz", "enabled": True},
        {"domain": "filesystem", "enabled": True},
    ]
    assert ma.installed_services() == ["qobuz"]
    assert ma.known_services() == ["tidal", "qobuz"]


def test_a_silent_play_is_blamed_on_the_provider_by_the_name_ma_gives_it(
        ma, ma_transport):
    # «<servizio> non è collegato» takes its subject from the backend. Read
    # out of the LMS table instead, a MusicAssistant provider comes back
    # spelled for another music system or not at all — and a sentence whose
    # subject is the empty string is not one the household can act on.
    ma_transport.responses["player_queues/get_active_queue"] = {"queue_id": "q1"}
    ma_transport.responses["player_queues/get"] = {
        "state": "idle", "current_index": 0, "elapsed_time": 0,
        "current_item": {"name": "Comfortably Numb"},
    }
    aimed = ma.for_service("apple_music")
    result = playback.started(aimed,
                              actions.ActionResult("Riproduco.", ok=True))
    assert result.ok is False
    assert str(result) == "Apple Music non è collegato."


def test_a_client_aimed_at_nothing_still_has_nothing_to_blame(ma, ma_transport):
    # The other half of the same rule: unaimed, MusicAssistant is searching
    # its own library and there is no service to name, so the check stands
    # down rather than inventing one (playback.after_play, UNREAD).
    assert playback.after_play(ma) == (None, playback.UNREAD)
    assert ma_transport.calls == []
