"""Every backend, checked against the contract the engine actually relies on.

``engine/`` has never held an ``LMSClient``. It calls methods on whatever
object it was handed, which is what makes a second music system possible at
all — and also what makes a missing method invisible until somebody speaks a
sentence that needs it. ``player/protocols.py`` writes that contract down;
this is where a backend is held to it.

Two promises are checked here, and the second is the one that would otherwise
rot. A backend must have the methods the protocols name. And a backend must
have the methods it *claims*: ``Capabilities`` is how the engine decides
whether to offer a feature at all, so a capability set to True with nothing
behind it turns a clean "this player cannot search" into an AttributeError
three frames down, reported to the listener as "the hi-fi is not answering" —
which is not true, and is the one kind of wrong answer this product exists to
avoid.

No network: every client here is built pointing at a host that does not
resolve, and nothing is ever called on it. Presence is the whole question.
"""

import pytest

from player.protocols import Capabilities, MusicLibrary, PlayerTransport
from player.registry import BACKENDS

#: Somewhere that cannot answer, because nothing here asks it anything.
NOWHERE = "http://player.invalid:9000"
SOME_PLAYER = "aa:bb:cc:dd:ee:ff"

#: What each capability promises exists. Deliberately spelled out again rather
#: than imported from the protocols: this table is the check, and a table that
#: derived itself from the thing it checks would agree with it always.
CAPABILITY_METHODS = {
    "search": ("search_tracks", "track_url", "album_candidates", "find_album",
               "album_tracks", "artist_candidates", "find_artist",
               "artist_tracks", "artist_top_tracks", "playlist_candidates",
               "find_playlist"),
    "local_library": ("local_album_candidates", "local_artist_candidates",
                      "local_track_candidates", "find_local_album",
                      "find_local_artist", "find_local_track",
                      "local_albums_by_artist", "blocking_service"),
    "favorites": ("favorites_items", "favorites_playlist_play"),
    "genres": ("local_genres", "play_local_genre"),
    "years": ("local_years", "play_local_year"),
    "browse_items": ("play_browse_item", "add_browse_item", "insert_browse_item",
                     "play_local_album", "add_local_album", "insert_local_album",
                     "play_local_artist", "add_local_artist", "insert_local_artist",
                     "play_local_track", "add_local_track", "insert_local_track"),
    "streamable": ("stream_urls",),
    "services": ("installed_services", "known_services", "can_search",
                 "can_play", "note_playback_failure",
                 "forget_playback_failure", "note_playback_started",
                 "settle_pending", "remember_silence_in", "silent_services",
                 "for_service"),
    "sleep_timer": ("sleep",),
    "seek": ("seek",),
    "multi_player": ("get_players", "for_player"),
    "artwork": ("status_info",),
}

#: The controls no music system is allowed to be without. Everything here acts
#: on the player in front of it and resolves nothing, which is why a speaker
#: with no catalogue at all still has to have them.
TRANSPORT_ALWAYS = (
    "pause", "resume", "next_track", "previous_track", "volume", "volume_set",
    "clear_queue", "queue_upcoming", "now_playing_info", "status_info",
    "play_url", "add_url", "insert_url", "play_tracks",
)

BACKEND_NAMES = sorted(BACKENDS)


def client_for(backend):
    return backend.build(NOWHERE, SOME_PLAYER, token="unused", timeout=1.0)


def test_at_least_one_backend_is_registered():
    # An empty registry passes every parametrized test below by vacuum, and
    # the first thing anyone would want to know is which backends exist.
    assert BACKEND_NAMES, "no backend registered — did discovery stop working?"


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_the_registry_key_is_the_backends_own_name(name):
    # --backend reads the key; a log line reads the name. They have to be the
    # same string or the flag that works is not the one printed.
    assert BACKENDS[name].name == name
    assert BACKENDS[name].label, f"{name} has no spoken label"


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_a_backend_can_be_built_without_touching_the_network(name):
    # Construction must be inert. The setup page builds a client to ask "is it
    # there?", and a constructor that dialled would make that question cost a
    # timeout before it was asked.
    assert client_for(BACKENDS[name]) is not None


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_every_backend_works_the_transport_controls(name):
    client = client_for(BACKENDS[name])
    missing = [m for m in TRANSPORT_ALWAYS if not hasattr(client, m)]
    assert missing == [], f"{name} cannot {', '.join(missing)}"
    assert isinstance(client, PlayerTransport)


def unkept_promises(capabilities, client):
    """``{capability: [methods it promised and has not got]}``.

    A function and not a loop inside the test below, so that the synthetic
    backends at the bottom of this file are held to the *same* check the real
    ones are. A second copy of this loop would agree with itself whatever the
    table said, which is exactly the kind of test that passes while the thing
    it guards rots.
    """
    missing = {}
    for capability, methods in CAPABILITY_METHODS.items():
        if not getattr(capabilities, capability):
            continue
        absent = [m for m in methods if not hasattr(client, m)]
        if absent:
            missing[capability] = absent
    return missing


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_a_backend_has_every_method_it_claims(name):
    backend = BACKENDS[name]
    missing = unkept_promises(backend.capabilities, client_for(backend))
    assert missing == {}, (
        f"{name} declares capabilities it has not got: {missing} — either "
        f"implement them or set the flag to False, because the engine offers "
        f"the feature on the strength of that flag alone")


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_a_searching_backend_is_a_whole_library(name):
    # Partial catalogues are the trap: enough of the protocol to be offered
    # the request, not enough to answer it.
    backend = BACKENDS[name]
    if not backend.capabilities.search:
        pytest.skip(f"{name} has no catalogue")
    assert isinstance(client_for(backend), MusicLibrary)


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_a_backend_knows_which_player_it_is_aimed_at(name):
    # http_api reads client.player_id to tell the page which room answered,
    # and multiroom compares it to decide whether to re-aim.
    assert getattr(client_for(BACKENDS[name]), "player_id", None) == SOME_PLAYER


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_re_aiming_at_the_same_player_costs_nothing(name):
    # ConversationState re-aims on every room turn. for_player is documented
    # to hand back the same object when there is nothing to change, and the
    # engine leans on that: it re-aims far more often than it moves.
    backend = BACKENDS[name]
    if not backend.capabilities.multi_player:
        pytest.skip(f"{name} has one player")
    client = client_for(backend)
    assert client.for_player(None) is client
    assert client.for_player(SOME_PLAYER) is client


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_a_probe_and_a_discovery_are_callable_or_absent(name):
    backend = BACKENDS[name]
    assert callable(backend.probe)
    # discover is None for a system that has to be told where it is. That is a
    # fact about the system, not an unfinished backend, so None is allowed and
    # anything else has to be callable.
    assert backend.discover is None or callable(backend.discover)


# -- the rows no registered backend reaches ------------------------------------
#
# ``streamable`` is declared in the protocols and claimed by nobody: LMS and
# MusicAssistant each drive players of their own, so neither needs a way to
# hand an id to somebody else's speakers. Every parametrized check above walks
# the registry, so none of them ever reaches that row of CAPABILITY_METHODS —
# and a row nothing reaches is a row that rots quietly until the day it is
# load-bearing. The first backend to claim it will be a catalogue that plays
# nothing at all, and by then the table has to already work.
#
# So the row is exercised here against two backends built for the purpose. They
# go through ``unkept_promises``, the same function the real ones go through:
# what is under test is the table, not a restatement of it.


class KeepsIt:
    """A catalogue that plays nothing: the shape the first one will have."""

    def stream_urls(self, item_id):
        return ["http://books.invalid/%s/01.m4b" % item_id]


class ClaimsItWithout:
    """The same declaration with nothing behind it — the bug being guarded."""


def test_the_streamable_row_accepts_a_backend_that_keeps_the_promise():
    assert unkept_promises(Capabilities(streamable=True), KeepsIt()) == {}


def test_the_streamable_row_catches_a_backend_that_does_not():
    # The failure this whole file exists for: a flag set to True with no
    # method behind it, which the engine would read as "offer the feature"
    # and pay for with an AttributeError reported as "the hi-fi is not
    # answering" — a sentence that is not true and cannot be acted on.
    assert unkept_promises(Capabilities(streamable=True), ClaimsItWithout()) == {
        "streamable": ["stream_urls"]}


def test_no_registered_backend_claims_streamable_yet():
    # The premise of the two tests above, written down: the day this fails is
    # the day a real backend covers the row and these synthetic ones stop
    # being the only thing that does.
    claiming = [n for n in BACKEND_NAMES if BACKENDS[n].capabilities.streamable]
    assert claiming == [], (
        f"{claiming} now claims streamable — good; check the parametrized "
        f"checks above cover it, and consider dropping the synthetic pair")
