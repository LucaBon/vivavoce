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

import actions
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

def make_multiroom(pro=True, players=PLAYERS, lms=None):
    """A MultiRoom over a static player list; pro=None means no license
    infrastructure at all (always gated). ``lms`` is the library the room-vs-
    title comparison consults — left out, it never second-guesses a room."""
    return MultiRoom(FakeLicense(pro) if pro is not None else None,
                     lambda: players, lms=lms)


def local_library(transport, albums=(), artists=(), tracks=(), loose=False):
    """Wire a local library onto the fake transport, honouring ``search:``.

    The search term is what makes these tests real. A fake that returns the
    same rows whatever it is asked would hand both readings of a phrase the
    same candidates, and every assertion below would pass on a comparison that
    never compared anything. ``loose=True`` is the other half of the same
    worry: ``engine/lms.py`` warns that LMS ``search:`` is a loose keyword
    match, so the verdict is checked against a server that ignores the term
    entirely as well as one that ANDs it.
    """
    def rows(kind, items, id_key, name_key):
        def handler(cmd):
            term = next((p.split("search:", 1)[1] for p in cmd
                         if str(p).startswith("search:")), "")
            words = term.lower().split()
            hits = [it for it in items
                    if loose or all(w in it[1].lower() for w in words)]
            # LMS truncates, and it truncates the BROADER query hardest — which
            # is the room-less reading, the one whose exact-title row is what
            # keeps a real room command safe. A fake that returns everything
            # would quietly test a comparison the server never performs.
            limit = int(cmd[3]) if len(cmd) > 3 and str(cmd[3]).isdigit() else len(hits)
            hits = hits[:limit]
            if not hits:
                return {"count": 0}
            return {f"{kind}_loop": [
                dict({id_key: i, name_key: title},
                     **({"artist": artist} if artist else {}))
                for i, title, artist in hits]}
        return handler

    transport.responses["albums"] = rows("albums", [
        (10 + i, t, a) for i, (t, a) in enumerate(_pairs(albums))], "id", "album")
    transport.responses["artists"] = rows("artists", [
        (20 + i, t, None) for i, (t, _a) in enumerate(_pairs(artists))], "id", "artist")
    transport.responses["titles"] = rows("titles", [
        (30 + i, t, a) for i, (t, a) in enumerate(_pairs(tracks))], "id", "title")


def _pairs(items):
    """Accept ``("Title", ...)`` or ``(("Title", "Artist"), ...)``."""
    return [(it, None) if isinstance(it, str) else it for it in items]


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


# -- pro/multiroom: the room reading is a guess, and the library settles it ---
#
# T2.7b. A player named after a word of a title used to take the turn outright:
# with «America» in the house, «metti breakfast in america» on a free install
# answered "that's a Pro feature" and played nothing — a record the listener
# owns, served with an advertisement. Both readings now go to the library and
# the better one wins. The verdict is the same for both licenses on purpose:
# which record the words name is not a thing a license gets a say in.

AMERICA = [{"playerid": "am:am", "name": "America"}]
BIANCO = [{"playerid": "bi:bi", "name": "Bianco"}]
CUCINA = [{"playerid": "bb:bb", "name": "Cucina"}]


#: Commands that actually touch the music. The library lookups the comparison
#: makes are server-level reads on player id "-", so "did anything happen, and
#: where" has to be asked of these and not of ``transport.calls`` wholesale.
_ACTS = ("playlistcontrol", "playlist", "pause", "play", "button", "mixer")


def _played(transport):
    return [cmd for _p, cmd in transport.calls if cmd[0] in _ACTS]


def _players_acted_on(transport):
    return {player for player, cmd in transport.calls if cmd[0] in _ACTS}


@pytest.mark.parametrize("loose", [False, True])
def test_a_title_ending_in_a_room_name_beats_the_room_on_free(lms, transport, loose):
    """The reproduction case, and the whole point of T2.7b."""
    local_library(transport, albums=["Breakfast in America"], loose=loose)
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert "Pro" not in reply, reply
    assert ["playlistcontrol", "cmd:load", "album_id:10"] in transport.commands()
    # ...and on the default player, not on the one called America.
    assert _players_acted_on(transport) == {"aa:bb:cc:dd:ee:ff"}


def test_a_title_ending_in_a_room_name_beats_the_room_on_pro(lms, transport):
    """One reading for both licenses. The Pro turn used to strip the phrase to
    «metti breakfast» and play whatever that found *in the America room*; it
    now plays the record the words actually name, where the listener is —
    **and says that is what it did**, which is the whole argument of T2.7a: a
    room the listener spoke out loud may not just vanish from the answer."""
    local_library(transport, albums=["Breakfast in America"])
    pro = Router(lms, multiroom=make_multiroom(pro=True, players=AMERICA, lms=lms))
    reply = str(pro.handle("metti breakfast in america", source="local"))
    assert msg("read_as_title").strip(" —") in reply, reply
    assert ["playlistcontrol", "cmd:load", "album_id:10"] in transport.commands()
    assert _players_acted_on(transport) == {"aa:bb:cc:dd:ee:ff"}


def test_the_overruled_room_is_not_announced_without_pro(lms, transport):
    """Free never had the room, so there is nothing to explain — and an
    explanation about multi-room in a reply to someone who does not have it is
    an advertisement, which is the thing T2.7 exists to stop."""
    local_library(transport, albums=["Breakfast in America"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert msg("read_as_title").strip(" —") not in reply, reply


@pytest.mark.parametrize("pro", [None, True])
@pytest.mark.parametrize("phrase", ["metti l'album breakfast in america",
                                    "riproduci l'album breakfast in america"])
def test_an_identified_album_is_rescued_too(lms, transport, pro, phrase):
    """The gate has to weigh the string the *route* would search.

    «metti l'album breakfast in america» is answered by step 5, which searches
    «breakfast in america» — but the gate used to consult only the generic
    branch and so measured «l'album breakfast in america», which no library
    contains. Result: the ad on free, and the record playing in the America
    room on Pro. The gate now walks the same branches the route does.
    """
    local_library(transport, albums=["Breakfast in America"])
    r = Router(lms, multiroom=make_multiroom(pro=pro, players=AMERICA, lms=lms))
    reply = str(r.handle(phrase, source="local"))
    assert "serve Pro" not in reply, reply
    assert ["playlistcontrol", "cmd:load", "album_id:10"] in transport.commands()
    assert _players_acted_on(transport) == {"aa:bb:cc:dd:ee:ff"}


def test_an_english_put_x_on_phrase_still_asks_the_library(lms, transport):
    """«put love on repeat» matches no play branch — the adjacent "put on" is
    not there and it does not end in "on" — so the gate used to hand the turn
    to a player called «Repeat» without asking whether the record exists."""
    players = [{"playerid": "re:re", "name": "Repeat"}]
    local_library(transport, tracks=["Love on Repeat"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=players, lms=lms))
    reply = str(free.handle("put love on repeat", source="local", lang="en"))
    # The library was consulted for both readings, and the room lost.
    terms = [p for cmd in transport.commands() for p in cmd
             if str(p).startswith("search:")]
    assert "search:love on repeat" in terms, transport.commands()
    assert "Pro" not in reply, reply
    assert _played(transport) == []
    # What it does *not* do is play, and that is a separate, pre-existing gap:
    # no route branch parses «put X on Y» either, so the turn ends in an honest
    # "I didn't get that" rather than an advertisement for a room nobody asked
    # for. Trading a wrong answer for no answer is the improvement here.
    assert reply == msg("router_fallback"), reply


def test_a_blocked_record_cannot_decide_the_reading(lms, transport):
    """Kid-safe. The resolvers refuse a blocked item anyway, but by then it has
    already swung the routing — and the refusal («c'è, ma non è adatta») tells
    a child the record is in the house, where the Pro pitch it replaced leaked
    nothing at all."""
    local_library(transport, albums=["Breakfast in America"])
    guard = actions.Guard(restricted=True, blocklist=["breakfast in america"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms),
                  kidsafe=_FixedGuard(guard))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert "Pro" in reply and "America" in reply, reply
    assert _played(transport) == []


class _FixedGuard:
    """The narrowest thing the router's kid-safe seam accepts."""

    def __init__(self, guard):
        self._guard = guard

    def guard_for(self, _client_id):
        return self._guard


def test_an_overruled_room_does_not_inherit_an_open_list_in_that_room(
        lms, transport):
    """A list opened «in cucina» retargets the follow-up pick to Cucina. When
    the gate then judges the next turn *not* to be about a room, that stale
    retarget must not capture it: the comment at the branch says «play it,
    here», and it has to be true."""
    local_library(transport, tracks=["Notte in bianco", "Notte in bianco 2"])
    players = [{"playerid": "bb:bb", "name": "Cucina"},
               {"playerid": "bi:bi", "name": "Bianco"}]
    pro = Router(lms, multiroom=make_multiroom(pro=True, players=players, lms=lms))
    pro.handle("metti notte in cucina", source="local")   # opens a list in Cucina
    pro.handle("metti notte in bianco", source="local")   # judged a title
    assert _players_acted_on(transport) <= {"aa:bb:cc:dd:ee:ff"}


def test_notte_in_bianco_beats_a_player_called_bianco(lms, transport):
    local_library(transport, tracks=["Notte in bianco"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=BIANCO, lms=lms))
    reply = str(free.handle("metti notte in bianco", source="local"))
    assert "Pro" not in reply, reply
    assert ["playlistcontrol", "cmd:load", "track_id:30"] in transport.commands()


@pytest.mark.parametrize("loose", [False, True])
def test_a_real_room_still_wins_over_a_title_that_shares_its_word(lms, transport, loose):
    """«bollicine in cucina» is a room command, and stays one."""
    local_library(transport, tracks=["Bollicine"], loose=loose)
    free = Router(lms, multiroom=make_multiroom(pro=None, players=CUCINA, lms=lms))
    reply = str(free.handle("metti bollicine in cucina", source="local"))
    assert "Pro" in reply and "Cucina" in reply, reply
    assert _played(transport) == []


def test_the_room_word_alone_is_not_a_title(lms, transport):
    """The trap the confidence floor exists for.

    With an album literally called «Cucina», the whole phrase matches *something*
    and the phrase without the room matches it less — so a bare "better than"
    comparison hands the turn to the title reading and starts music in the
    living room without saying so. That is rejected approach #1 coming back
    through the side door; ``TITLE_MIN_SCORE`` is what shuts it.
    """
    local_library(transport, albums=["Cucina"], loose=True)
    free = Router(lms, multiroom=make_multiroom(pro=None, players=CUCINA, lms=lms))
    reply = str(free.handle("metti musica rilassante in cucina", source="local"))
    assert "Pro" in reply, reply
    assert _played(transport) == []


def test_a_remastered_tag_does_not_hand_the_turn_back_to_the_room(lms, transport):
    """Nobody's library is tagged as tidily as a reproduction table.

    With ``_score``'s subset floor on, «breakfast in america» and «breakfast»
    both score 0.95 against a title carrying an edition suffix — a tie, and a
    tie keeps the room. Off, they separate 0.886 to 0.760 and the record plays.
    """
    local_library(transport, albums=["Breakfast In America (Remastered 2010)"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert "Pro" not in reply, reply
    assert ["playlistcontrol", "cmd:load", "album_id:10"] in transport.commands()


@pytest.mark.parametrize("pro", [None, True])
def test_a_room_shaped_title_does_not_steal_a_real_room_command(lms, transport, pro):
    """«metti musica in cucina» — the most ordinary way in Italian to ask for
    music in the kitchen — against a library that happens to hold an album
    called *Musica in Cucina*.

    Both readings are strong here (1.000 against 0.818), so the title wins and
    the record plays where the listener is. That is defensible: the words *are*
    the name of something they own. What is not defensible is doing it in
    silence, and on Pro this used to drop a room the listener said out loud
    with nothing in the reply to show for it. Now the answer says which reading
    it took, so a wrong guess is one sentence away from being corrected.
    """
    local_library(transport, albums=["Musica in Cucina"])
    r = Router(lms, multiroom=make_multiroom(pro=pro, players=CUCINA, lms=lms))
    reply = str(r.handle("metti musica in cucina", source="local"))
    assert ["playlistcontrol", "cmd:load", "album_id:10"] in transport.commands()
    assert _players_acted_on(transport) == {"aa:bb:cc:dd:ee:ff"}
    said_so = msg("read_as_title").strip(" —") in reply
    assert said_so is bool(pro), reply


# Songs named after rooms are not a curiosity, they are a genre. This battery
# is the English half of it, and it found the one shape the rest do not have.
ROOM_SONGS = [
    ("Bedroom Floor", "Bedroom", "play bedroom floor"),
    ("Kitchen", "Kitchen", "play kitchen"),
    ("Kitchen Door", "Kitchen", "play kitchen door"),
    ("Cold Kitchen", "Kitchen", "play cold kitchen"),
    ("Bathroom Window", "Bathroom", "play bathroom window"),
    ("She Came In Through the Bathroom Window", "Bathroom",
     "play she came in through the bathroom window"),
    ("Bathroom Dance", "Bathroom", "play bathroom dance"),
    ("Sitting in the Living Room", "Living Room",
     "play sitting in the living room"),
    ("Laundry Room", "Laundry Room", "play laundry room"),
    ("Empty Attic", "Attic", "play empty attic"),
    ("In My Room", "Room", "play in my room"),
]


@pytest.mark.parametrize("pro", [None, True])
@pytest.mark.parametrize("title,room,phrase", ROOM_SONGS)
def test_a_song_named_after_a_room_plays(lms, transport, title, room, phrase, pro):
    """Every one of these plays the record, on either licence.

    Most never reach the gate at all — no room preposition sits where
    ``extract_room`` looks, so «play bathroom window» is simply a title. Two do
    reach it («sitting **in** the living room» and «**in** my room») and are
    saved by the weighing. Keeping the safe ones here anyway is the point: they
    document where the cheap filter ends and the expensive one begins, and they
    fail loudly if a future preposition widens the first.
    """
    local_library(transport, tracks=[title])
    players = [{"playerid": "rr:rr", "name": room}]
    r = Router(lms, multiroom=make_multiroom(pro=pro, players=players, lms=lms))
    reply = str(r.handle(phrase, source="local", lang="en"))
    assert "Pro" not in reply, reply
    assert ("aa:bb:cc:dd:ee:ff",
            ["playlistcontrol", "cmd:load", "track_id:30"]) in transport.calls


@pytest.mark.parametrize("pro", [None, True])
def test_a_room_that_leaves_nothing_to_play_is_the_title(lms, transport, pro):
    """«play in my room», against a player actually called «My Room».

    Stripping the room leaves a bare «play», which names nothing — and that is
    not a reason to stop asking, it is the strongest evidence available that
    the room word was the title, because the room reading has nothing left to
    act on. Before this, the turn short-circuited to the room and Pro answered
    «Resuming playback in My Room»: the wrong song, in a room nobody named.
    """
    local_library(transport, tracks=["In My Room"])
    players = [{"playerid": "rr:rr", "name": "My Room"}]
    r = Router(lms, multiroom=make_multiroom(pro=pro, players=players, lms=lms))
    reply = str(r.handle("play in my room", source="local", lang="en"))
    assert "Pro" not in reply, reply
    assert ("aa:bb:cc:dd:ee:ff",
            ["playlistcontrol", "cmd:load", "track_id:30"]) in transport.calls


@pytest.mark.parametrize("pro", [None, True])
def test_the_same_shape_still_resumes_when_the_record_is_not_there(
        lms, transport, pro):
    """The other half of it, and the reason the library has to be asked rather
    than the shape assumed: «play in the kitchen» with no such record is what
    it also is — resume, in the kitchen."""
    local_library(transport, tracks=["Something Else"])
    players = [{"playerid": "rr:rr", "name": "Kitchen"}]
    r = Router(lms, multiroom=make_multiroom(pro=pro, players=players, lms=lms))
    reply = str(r.handle("play in the kitchen", source="local", lang="en"))
    if pro:
        # It resumes, and it resumes IN THE ROOM — the room reading was right.
        assert reply.endswith("in Kitchen."), reply
        assert ("rr:rr", ["pause", "0"]) in transport.calls, transport.calls
    else:
        assert "Pro" in reply and "Kitchen" in reply, reply
        assert _played(transport) == []


@pytest.mark.parametrize("phrase,room", [
    ("metti Shpalman romanza da salotto", "Salotto"),
    ("metti musica da camera", "Camera"),
    ("metti un valzer da sala", "Sala"),
])
def test_da_names_a_kind_of_music_not_a_room(lms, transport, phrase, room):
    """«da» is not a room preposition, and these are why.

    Italian names genres with it — chamber music, parlour romance, ballroom
    waltz — and Camera, Salotto and Sala are what people call their rooms. If
    «da» were in `_PREPS`, every one of these would be a command for a room,
    and it would be stolen *before* the library ever got a say: the preposition
    list runs first, and a phrase it captures never reaches the weighing.

    So the assertion is about `extract_room` and not about the reply: nothing
    here may be seen as a room in the first place.
    """
    players = [{"playerid": "aa:aa", "name": room}]
    mr = make_multiroom(pro=True, players=players, lms=lms)
    assert mr.extract_room(phrase, "it") == (phrase, None)
    # ...while the same room, asked for the way Italians actually ask, works.
    assert mr.extract_room(f"metti Shpalman in {room.lower()}", "it")[1] is not None


@pytest.mark.parametrize("loose", [False, True])
@pytest.mark.parametrize("pro", [None, True])
def test_a_song_named_after_a_room_does_not_confuse_either_reading(
        lms, transport, pro, loose):
    """*La cucina* (Irene Grandi), against a player called «Cucina».

    The worst shape this comparison can be handed: the title IS the room name,
    give or take an article. It holds, and the article is why — the dangerous
    case is not "the title contains the room word", it is "the title *equals*
    the sentence minus the verb", and «la cucina in cucina» equals nothing
    (0.657, under the floor) while «la cucina» equals the track exactly
    (1.000). So the room reading wins every phrase that names a room, and
    «metti la cucina» — which names none — plays the song.

    Parametrized over a strict and a loose server because the article is doing
    load-bearing work here, and it should not matter what the search returns.
    """
    local_library(transport, tracks=[("La cucina", "Irene Grandi")],
                  artists=["Irene Grandi"], loose=loose)
    r = Router(lms, multiroom=make_multiroom(pro=pro, players=CUCINA, lms=lms))

    # No room in the sentence: the song plays, on either licence.
    assert "Pro" not in str(r.handle("metti la cucina", source="local"))
    assert ["playlistcontrol", "cmd:load", "track_id:30"] in transport.commands()

    # A room in the sentence: it stays a room command and behaves as before.
    transport.calls.clear()
    reply = str(r.handle("metti la cucina in cucina", source="local"))
    if pro:
        assert reply.endswith("in Cucina."), reply
        assert ("bb:bb", ["playlistcontrol", "cmd:load", "track_id:30"]) in transport.calls
    else:
        assert "Pro" in reply and "Cucina" in reply, reply
        assert _played(transport) == []


def test_the_room_survives_when_the_shorter_reading_is_truncated_away(
        lms, transport):
    """The union pool cannot repair truncation, so this pins what it does.

    The room-less query «notte» is the broader one, so LMS answers it with ten
    rows and the exact *Notte* is not necessarily among them. With it present
    both readings tie at 1.000 and the room keeps the turn; the point of this
    test is that a real room command is decided by which rows came back, and
    that fact is exercised rather than assumed.
    """
    filler = [f"Notte {i}" for i in range(1, 10)]
    local_library(transport, tracks=["Notte in bianco", "Notte"] + filler)
    free = Router(lms, multiroom=make_multiroom(pro=None, players=BIANCO, lms=lms))
    reply = str(free.handle("metti notte in bianco", source="local"))
    assert "Pro" in reply and "Bianco" in reply, reply
    assert _played(transport) == []


def test_what_the_comparison_costs(lms, transport):
    """The bill, pinned, because it is paid on the free tier too.

    A room-shaped play used to cost nothing before the route ran. It now costs
    one round of three searches when the library has never heard of the whole
    phrase — the ordinary room command — and two rounds when it has. The gate
    does not share its lookups with the resolver that runs next, so the winning
    phrase is searched again downstream; that duplicate is visible here rather
    than discovered on a Raspberry Pi.
    """
    def searches():
        return [p for cmd in transport.commands() for p in cmd
                if str(p).startswith("search:")]

    # Nothing answers «bollicine in cucina»: one round, and the room keeps it.
    local_library(transport, tracks=["Bollicine"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=CUCINA, lms=lms))
    free.handle("metti bollicine in cucina", source="local")
    assert searches() == ["search:bollicine in cucina"] * 3

    # The whole phrase does answer: two rounds in the gate, then the resolver
    # searches the winner again on its own.
    transport.calls.clear()
    local_library(transport, albums=["Breakfast in America"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    free.handle("metti breakfast in america", source="local")
    assert searches().count("search:breakfast in america") == 6
    assert searches().count("search:breakfast") == 3


def test_a_transport_command_never_asks_the_library(lms, transport):
    """«pausa in cucina» has no title in it, so there is nothing to weigh."""
    local_library(transport, tracks=["Bollicine"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=CUCINA, lms=lms))
    reply = str(free.handle("pausa in cucina"))
    assert "Pro" in reply, reply
    assert transport.calls == []


def test_the_prefix_form_costs_no_library_lookup(lms, transport):
    """«in cucina metti X» — the room word is nowhere near the title."""
    local_library(transport, tracks=["Bollicine"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=CUCINA, lms=lms))
    reply = str(free.handle("in cucina metti bollicine"))
    assert "Pro" in reply, reply
    assert transport.calls == []


def test_the_comparison_is_english_too(lms, transport):
    players = [{"playerid": "pa:pa", "name": "Paradise"}]
    local_library(transport, tracks=["Lost in Paradise"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=players, lms=lms))
    reply = str(free.handle("play lost in paradise", source="local", lang="en"))
    assert "Pro" not in reply, reply
    assert ["playlistcontrol", "cmd:load", "track_id:30"] in transport.commands()


def test_a_player_named_like_a_title_word_with_no_such_track(lms, transport):
    """We cannot play what is not there, so the room reading is the only one
    that explains the words."""
    local_library(transport, tracks=["Notte prima degli esami"])
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert "Pro" in reply and "America" in reply, reply
    assert _played(transport) == []


@pytest.mark.parametrize("loose", [False, True])
def test_a_library_holding_both_readings_keeps_the_room(lms, transport, loose):
    """When the library owns *Notte* AND *Notte in bianco*, and a player is
    called «Bianco», the words genuinely mean either thing — both readings
    score 1.000. A tie is not a reason to act, so the room keeps the turn and
    the Pro pitch stands. The residual is real and deliberate: this fix makes
    the defect rare, it does not abolish it.
    """
    local_library(transport, tracks=["Notte", "Notte in bianco"], loose=loose)
    free = Router(lms, multiroom=make_multiroom(pro=None, players=BIANCO, lms=lms))
    reply = str(free.handle("metti notte in bianco", source="local"))
    assert "Pro" in reply and "Bianco" in reply, reply
    assert _played(transport) == []


def test_an_empty_library_falls_back_to_the_pro_pitch(lms, transport):
    local_library(transport)
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert "Pro" in reply, reply
    # Three searches, not six: nothing answered the whole phrase, so the second
    # reading is never looked up.
    assert len(transport.calls) == 3


def test_an_unreachable_lms_falls_back_to_the_pro_pitch(lms, transport):
    transport.raise_on.update({"albums", "artists", "titles"})
    free = Router(lms, multiroom=make_multiroom(pro=None, players=AMERICA, lms=lms))
    reply = str(free.handle("metti breakfast in america", source="local"))
    assert "Pro" in reply and "America" in reply, reply
    assert _played(transport) == []


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
