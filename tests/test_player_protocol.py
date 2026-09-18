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

from player.protocols import (EVERYTHING, Capabilities, MusicLibrary,
                              PlayerTransport, SpokenLibrary, supports,
                              system_label)
from player.registry import BACKENDS, LIBRARIES

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
    # The Router opens one of these around every spoken turn, on whatever
    # client it was handed: a backend without it fails at the first sentence,
    # not at some feature nobody uses.
    "turn_deadline",
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
def test_a_backend_says_out_loud_what_it_is_called(name):
    # «{service} non è collegato. Apri le impostazioni di …» — the engine
    # cannot know which music system it is holding, so it asks the client, and
    # the answer has to be the same one the log lines use. For five languages
    # the catalogs said "LMS" outright, which sent every MusicAssistant
    # household to a settings page that does not exist.
    backend = BACKENDS[name]
    assert system_label(client_for(backend)) == backend.label, (
        f"{name}: the label on the registry declaration and the one on the "
        f"client disagree, so a reply and a log line name different systems")


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


# -- libraries: catalogues that play nothing -----------------------------------
#
# Declared as SPOKEN_LIBRARY, not BACKEND (player/registry.py says why), so none of the
# checks above reach them: they have no player and owe no transport. What they
# owe instead is the SpokenLibrary protocol and ``streamable`` — a catalogue
# that can neither play an item nor say where its files are has nothing to
# offer — and they go through ``unkept_promises`` like everyone else.

LIBRARY_NAMES = sorted(LIBRARIES)


def library_client_for(library):
    return library.build(NOWHERE, token="unused", timeout=1.0)


def test_at_least_one_library_is_registered():
    assert LIBRARY_NAMES, "no library registered — did discovery stop working?"


def test_no_name_means_a_backend_and_a_library_at_once():
    assert set(BACKEND_NAMES).isdisjoint(LIBRARY_NAMES)


@pytest.mark.parametrize("name", LIBRARY_NAMES)
def test_a_librarys_key_is_its_own_name(name):
    assert LIBRARIES[name].name == name
    assert LIBRARIES[name].label, f"{name} has no spoken label"


@pytest.mark.parametrize("name", LIBRARY_NAMES)
def test_a_library_says_out_loud_what_it_is_called(name):
    library = LIBRARIES[name]
    assert system_label(library_client_for(library)) == library.label


@pytest.mark.parametrize("name", LIBRARY_NAMES)
def test_a_library_is_a_spoken_catalogue_built_without_the_network(name):
    client = library_client_for(LIBRARIES[name])
    assert isinstance(client, SpokenLibrary)
    assert callable(LIBRARIES[name].probe)


@pytest.mark.parametrize("name", LIBRARY_NAMES)
def test_a_library_can_hand_its_files_to_someone_elses_speakers(name):
    library = LIBRARIES[name]
    assert library.capabilities.streamable, (
        f"{name} is a catalogue that plays nothing and cannot say where its "
        f"files are, so there is no way to hear anything in it")
    assert unkept_promises(library.capabilities,
                           library_client_for(library)) == {}


@pytest.mark.parametrize("name", LIBRARY_NAMES)
def test_a_library_claims_nothing_only_a_player_could_keep(name):
    # A shelf of books claiming ``search`` would be offered «metti Comfortably
    # Numb»; claiming ``seek`` or ``sleep_timer`` would be promising controls
    # that belong to the speakers it is heard through.
    claimed = {c for c in ("search", "local_library", "favorites", "genres",
                           "years", "browse_items", "services", "sleep_timer",
                           "seek", "multi_player", "artwork")
               if getattr(LIBRARIES[name].capabilities, c)}
    assert claimed == set(), f"{name} claims {sorted(claimed)}"


# -- the row a real library now covers, and the failure it cannot show ---------
#
# ``streamable`` was for a while claimed by nobody, and a synthetic pair here
# kept its row of CAPABILITY_METHODS from rotting. A registered library now
# walks that row through ``unkept_promises`` above. What a real library cannot
# show is the row *refusing* something, so the backend that declares the flag
# with nothing behind it stays.


class ClaimsItWithout:
    """A streamable declaration with nothing behind it — the bug being guarded."""


def test_the_streamable_row_catches_a_backend_that_does_not_keep_it():
    # The failure this whole file exists for: a flag set to True with no
    # method behind it, which the engine would read as "offer the feature"
    # and pay for with an AttributeError reported as "the hi-fi is not
    # answering" — a sentence that is not true and cannot be acted on.
    assert unkept_promises(Capabilities(streamable=True), ClaimsItWithout()) == {
        "streamable": ["stream_urls"]}


def test_a_registered_library_really_covers_the_streamable_row():
    # The premise of dropping the synthetic backend that kept the promise.
    assert any(LIBRARIES[n].capabilities.streamable for n in LIBRARY_NAMES)


def test_no_music_system_claims_streamable():
    # Both drive players of their own; a backend claiming it would be the
    # first to hand its ids to someone else's speakers, which is worth
    # noticing rather than slipping in.
    claiming = [n for n in BACKEND_NAMES if BACKENDS[n].capabilities.streamable]
    assert claiming == []


# -- asking, which is the half that was missing --------------------------------
#
# The Capabilities table said "the engine asks before it offers" and nothing
# asked: no engine module and no Router read it, so a backend without a
# catalogue answered a search with AttributeError three frames down, reported
# as «non riesco a contattare l'impianto» — a lie about a hi-fi that is
# answering perfectly. These tests are about the asking.

@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_a_client_the_registry_built_carries_what_it_can_do(name):
    # The engine holds a client, not a registry entry. If the declaration does
    # not travel with the client, the engine has nothing to ask.
    backend = BACKENDS[name]
    client = backend.client(NOWHERE, SOME_PLAYER, token="unused", timeout=1.0)
    assert client.capabilities == backend.capabilities


@pytest.mark.parametrize("name", BACKEND_NAMES)
def test_the_declaration_survives_being_re_aimed(name):
    # for_player and for_service hand back shallow copies, and a copy that
    # forgot what it could do would be a different backend halfway through a
    # turn — «metti Time in cucina» is one of those copies.
    backend = BACKENDS[name]
    client = backend.client(NOWHERE, SOME_PLAYER, token="unused", timeout=1.0)
    if supports(client, "multi_player"):
        assert client.for_player("other").capabilities == backend.capabilities
    if supports(client, "services"):
        # Un nome fisso: known_services() lo chiederebbe al server, e qui non
        # c'è rete (NOWHERE non risolve, ed è il punto).
        assert client.for_service("tidal").capabilities == backend.capabilities


def test_supports_reads_the_declaration():
    class Speakers:
        capabilities = Capabilities(search=True, multi_player=True)

    speakers = Speakers()
    assert supports(speakers, "search") is True
    assert supports(speakers, "multi_player") is True
    assert supports(speakers, "local_library") is False
    assert supports(speakers, "favorites") is False


def test_a_client_that_declares_nothing_is_taken_to_do_everything():
    """The migration has to be silent for anything built by hand — every test
    in this repo, and anybody embedding the engine. Refusing what a client
    never denied would turn a missing stamp into a missing feature.
    """
    class Homemade:
        pass

    for field in Capabilities.__dataclass_fields__:
        assert supports(Homemade(), field) is True


def test_everything_means_every_field():
    # Built from the dataclass, so a capability added to the table is covered
    # without a second list to forget.
    for field in Capabilities.__dataclass_fields__:
        assert getattr(EVERYTHING, field) is True


def test_an_unknown_capability_is_a_typo_not_an_answer():
    # A misspelt capability must not read as "no": that would disable a
    # feature quietly, which is the failure this whole table exists to avoid.
    with pytest.raises(AttributeError):
        supports(object(), "can_make_coffee")

