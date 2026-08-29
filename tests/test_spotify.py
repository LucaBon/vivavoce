"""Spotify, through the Spotty plugin.

Two things make this service different from TIDAL and Qobuz, and both are the
reason it has a file of its own:

* **the registry key is not the plugin tag.** People say "spotify"; LMS answers
  to ``spotty``. Everything user-facing keys on the first and everything on the
  wire keys on the second, and the only place the two meet is ``ServiceSpec``;

* **its feed does not have the shape the other two share**, which is why the
  fixtures here are hand-built instead of using ``make_feed``. Every shape below
  was read off a live LMS 9.0.3 + Spotty on 2026-08-28:

  - there is **no Songs category**. The search node answers with the category
    links (Artists, Albums, Playlists, Podcasts, Podcast Episodes, Users) and
    the matching tracks as their *siblings*, flagged ``isaudio``;
  - a track carries **no url** — ``{"id", "name", "isaudio", "hasitems"}`` and
    nothing more. The url is the name of its single ``type == "audio"`` child;
  - title, artist and album arrive as **one string**, "T by A from B".

  It also needs Spotify Premium, because Spotty plays through Spotify Connect:
  on a free account the plugin's whole menu is one "credentials missing"
  notice. That state is tested too — it is what most misconfigured installs
  will look like.

And one difference that is not about the feed at all: Spotify's search answers
every query, so the "trust the ranking" fallback is off for it. The last two
tests in this file are that rule and its limit.
"""

import pytest

from lms import SERVICES, LMSClient, uri_kind


@pytest.fixture
def spotify(transport):
    return LMSClient(base_url="http://lms.local:9000",
                     player_id="aa:bb:cc:dd:ee:ff",
                     transport=transport, service="spotify")


# -- the key/tag split ---------------------------------------------------------

def test_the_registry_key_is_the_word_people_say():
    # «da spotify metti X» is the phrase; "spotty" is what nobody says out loud.
    # localvoice/parsing.py builds the spoken-name regex from the key, so if
    # these two were ever swapped the sentence would stop parsing.
    assert "spotify" in SERVICES
    assert "spotty" not in SERVICES
    assert SERVICES["spotify"].tag == "spotty"


def test_for_service_switches_tag_but_shares_the_connection(lms):
    s = lms.for_service("spotify")
    assert s is not lms
    assert s.service.tag == "spotty"
    assert s._transport is lms._transport
    assert s.player_id == lms.player_id


def test_commands_go_out_under_the_plugin_tag(spotify, transport):
    transport.responses["spotty"] = {"loop_loop": []}
    spotify.search_node_id()
    assert transport.commands()[0][0] == "spotty", (
        "the feed was asked for under the wrong name: LMS has no 'spotify' app")


# -- URI classification ---------------------------------------------------------

@pytest.mark.parametrize("uri,kind", [
    ("spotify://track:4uLU6hMCjMI75M1A2tKUQC", "track"),
    ("spotify://album:1DFixLWuPkv3KT3TnV35m3", "album"),
    ("spotify://artist:0k17h0D3J5VfsdmQ1iZtE9", "artist"),
    ("spotify://playlist:37i9dQZF1DXcBWIGoYBM5M", "playlist"),
])
def test_uri_kind_reads_spotify_forms(uri, kind):
    assert uri_kind(uri) == kind


def test_a_foreign_uri_is_still_unclassified():
    assert uri_kind("http://example.com/song.mp3") is None


# -- the feed, as Spotty really answers it --------------------------------------

# Verbatim shapes from the live plugin (2026-08-28, query "money"), trimmed to
# the keys the client reads. The category links come first and the tracks are
# their siblings — that adjacency is the thing this service does differently.
SEARCH_CHILDREN = [
    {"name": "Artists", "isaudio": 0, "hasitems": 1, "id": "1.0_money.0"},
    {"name": "Albums", "isaudio": 0, "hasitems": 1, "id": "1.0_money.1"},
    {"name": "Playlists", "isaudio": 0, "hasitems": 1, "id": "1.0_money.2"},
    {"name": "Money For Nothing by Dire Straits from The Best Of Dire Straits",
     "isaudio": 1, "hasitems": 1, "id": "1.0_money.6"},
    {"name": "Money, Money, Money by ABBA from Arrival",
     "isaudio": 1, "hasitems": 1, "id": "1.0_money.10"},
]
TRACK_URL = "spotify://track:01Txvu3dNthhldq8oR0Pae"


def spotty_feed(children=None, url=TRACK_URL, search_node=True,
                audio_child=True):
    """A Spotty app feed, shaped the way the live plugin answers.

    Three things here are the plugin's and not a convenience:

    * the home menu has **no** ``type: "search"`` node. "Search" is a plain
      link whose child ``1.0`` / "New Search" is the search node — so this
      exercises the ``search_parents`` path, which is the one Spotty takes and
      which no fixture used to reach;
    * results come back under the search node with the category links first
      and the tracks as their siblings;
    * a track's ``menu:1`` node answers in **``item_loop``** with the url in
      ``text`` and in ``presetParams.favorites_url`` — and **no ``name`` key**.
    """
    kids = SEARCH_CHILDREN if children is None else children

    def handler(cmd):
        params = cmd[2:]
        item_id = next((p[len("item_id:"):] for p in params
                        if p.startswith("item_id:")), None)
        if item_id is None:                       # home menu: a link, not a search
            home = [{"id": "0", "name": "Home", "type": "link", "hasitems": 1}]
            if search_node:
                home.append({"id": "1", "name": "Search", "type": "link",
                             "hasitems": 1})
            return {"loop_loop": home}
        if item_id == "1":                        # ... whose child is the node
            return {"loop_loop": [
                {"id": "1.0", "name": "New Search", "type": "search",
                 "hasitems": 1},
                {"id": "1.1", "name": "an earlier search", "type": "link",
                 "hasitems": 1},
            ]}
        if item_id == "1.0":                      # the search node -> results
            return {"loop_loop": kids}
        # a track node under menu:1 -> its audio child, verbatim shape
        if not audio_child:
            return {"item_loop": [{"type": "link", "text": url}]}
        return {"item_loop": ([{"type": "audio", "text": url, "goAction": "play",
                                "presetParams": {"favorites_url": url}}]
                              if url else [])}

    return handler


def test_the_search_node_is_the_child_of_a_plain_search_link(spotify,
                                                             transport):
    # Spotty's home menu has no type=="search" node at all: search_node_id has
    # to enter the "Search" link and look again. That is what search_parents is
    # for, and without this test the whole file passed with it removed.
    transport.responses["spotty"] = spotty_feed()
    assert "search" in SERVICES["spotify"].search_parents
    assert spotify.search_node_id() == "1.0"


def test_tracks_are_read_from_beside_the_categories_not_from_a_songs_node(
        spotify, transport):
    # The difference from TIDAL and Qobuz in one assertion: there is no Songs
    # category to enter, and the tracks are still found.
    transport.responses["spotty"] = spotty_feed()
    assert "Songs" not in SERVICES["spotify"].category_aliases
    assert spotify.search_tracks("money") == [
        {"item_id": "1.0_money.6", "title": "Money For Nothing",
         "artist": "Dire Straits",
         "album": "The Best Of Dire Straits"},
        {"item_id": "1.0_money.10", "title": "Money, Money, Money",
         "artist": "ABBA", "album": "Arrival"},
    ]


def test_the_category_links_are_not_mistaken_for_tracks(spotify, transport):
    # They sit in the same list; only ``isaudio`` tells them apart.
    transport.responses["spotty"] = spotty_feed()
    assert all(t["title"] not in ("Artists", "Albums", "Playlists")
               for t in spotify.search_tracks("money"))


def test_a_title_containing_by_keeps_it(spotify, transport):
    # The split is greedy on the title for this reason: titles contain " by "
    # all the time and artists essentially never do. Non-greedy would have
    # called this song "Killed" by "Death by Motorhead".
    transport.responses["spotty"] = spotty_feed(children=[
        {"name": "Killed by Death by Motorhead from No Remorse",
         "isaudio": 1, "hasitems": 1, "id": "x.1"}])
    assert spotify.search_tracks("killed") == [
        {"item_id": "x.1", "title": "Killed by Death", "artist": "Motorhead",
         "album": "No Remorse"}]


def test_a_name_that_does_not_split_is_kept_whole_as_the_title(spotify,
                                                               transport):
    # Better a track with no artist than a track with an invented one.
    transport.responses["spotty"] = spotty_feed(children=[
        {"name": "Untitled", "isaudio": 1, "hasitems": 1, "id": "x.1"}])
    assert spotify.search_tracks("untitled") == [
        {"item_id": "x.1", "title": "Untitled"}]


# -- the url, fetched one level down --------------------------------------------

def test_track_url_reads_the_audio_child(spotify, transport):
    transport.responses["spotty"] = spotty_feed()
    assert spotify.track_url("1.0_money.6") == TRACK_URL


def test_track_url_ignores_a_child_that_is_not_audio(spotify, transport):
    # Spotty ships "go to album" / "go to artist" entries on this node. Those
    # carry spotify:// uris too, and handing one to play_url would start a
    # whole album for a request for one song — quietly.
    transport.responses["spotty"] = spotty_feed(audio_child=False)
    assert spotify.track_url("1.0_money.6") is None


def test_track_url_refuses_a_uri_that_is_not_a_track(spotify, transport):
    # The service scheme alone is not enough: spotify://album: matches it.
    transport.responses["spotty"] = spotty_feed(
        url="spotify://album:1DFixLWuPkv3KT3TnV35m3")
    assert spotify.track_url("1.0_money.6") is None


def test_track_url_survives_a_non_string_field(spotify, transport):
    # LMS menu modes put dicts in fields that are strings elsewhere.
    def handler(cmd):
        if any(str(p).startswith("item_id:") for p in cmd[2:]):
            return {"item_loop": [{"type": "audio", "text": {"nested": 1},
                                   "presetParams": {"favorites_url": TRACK_URL}}]}
        return {"loop_loop": []}

    transport.responses["spotty"] = handler
    assert spotify.track_url("x") == TRACK_URL


def test_track_url_is_none_when_the_child_is_not_a_spotify_uri(spotify,
                                                               transport):
    # Checked against the service's own scheme rather than taken on trust, so a
    # feed that changes shape yields None instead of something unplayable.
    transport.responses["spotty"] = spotty_feed(url="http://example.com/x.mp3")
    assert spotify.track_url("1.0_money.6") is None


def test_the_search_does_not_resolve_a_url_for_every_result(spotify, transport):
    # Twenty results, at most one ever played: resolving them all would be
    # twenty round trips for nineteen answers nobody wants.
    transport.responses["spotty"] = spotty_feed()
    spotify.search_tracks("money")
    entered = [c for c in transport.commands()
               if any(str(p).startswith("item_id:1.0_money.6") for p in c)]
    assert entered == []


# -- what the two halves do together --------------------------------------------

def test_playing_resolves_the_url_of_the_chosen_track_only(spotify, transport):
    import actions

    transport.responses["spotty"] = spotty_feed()
    res = actions.play_song(spotify, "Money For Nothing dei Dire Straits")
    assert res.ok
    assert ["playlist", "play", TRACK_URL] in transport.commands()
    # exactly one track was entered: the one that played
    entered = [c for c in transport.commands()
               if any(str(p).startswith("item_id:1.0_money.") for p in c)
               and "menu:1" in c]
    assert len(entered) == 1


def test_a_track_whose_url_cannot_be_resolved_does_not_play(spotify, transport):
    import actions

    transport.responses["spotty"] = spotty_feed(url=None)
    res = actions.play_song(spotify, "Money For Nothing dei Dire Straits")
    assert res.ok is False
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands()), (
        "nothing may be sent to the player when the url could not be found")


# -- the states a misconfigured install is in -----------------------------------

def test_a_logged_out_plugin_finds_nothing(spotify, transport):
    # Verbatim from the live plugin before it was given an account. This is
    # also what an install without Premium looks like, permanently.
    transport.responses["spotty"] = {"loop_loop": [
        {"id": "ca3654c9.0", "type": "textarea", "hasitems": 1,
         "name": "Spotify Credentials missing\nPlease check Settings"},
    ]}
    assert spotify.search_node_id() is None
    assert spotify.search_tracks("money") == []


def test_no_search_node_finds_nothing(spotify, transport):
    transport.responses["spotty"] = spotty_feed(search_node=False)
    assert spotify.search_tracks("money") == []


# -- the promise that costs a feature -------------------------------------------

def test_a_search_that_always_answers_is_not_trusted_to_rank(spotify,
                                                             transport):
    # Measured on the live plugin: «zzzzqqqxyzzy» returns fourteen tracks from
    # Spotify and *zero* from TIDAL and Qobuz. The "no title matched, play the
    # top result" fallback is a bet on the ranking that only pays where an empty
    # answer is possible — so Spotify does not take it, and says so instead.
    import actions

    transport.responses["spotty"] = spotty_feed(children=[
        {"name": "La sigla di Bluey by Bluey from Bluey",
         "isaudio": 1, "hasitems": 1, "id": "x.1"}])
    res = actions.play_song(spotify, "zzzzqqqxyzzy")
    assert res.ok is False
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands()), (
        "a song nobody asked for was started, in silence")


def test_the_other_services_still_trust_their_ranking(lms, transport,
                                                      make_feed):
    # The flag is per service and the change must not reach the two whose
    # empty answers make the fallback safe: TIDAL returning a result at all is
    # itself the evidence.
    import actions

    assert SERVICES["tidal"].trust_ranking is True
    assert SERVICES["qobuz"].trust_ranking is True
    transport.responses["tidal"] = make_feed(
        search_node="7", categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc",
                      "text": "Something Else\nA Band"}]})
    res = actions.play_song(lms, "a title that matches nothing here")
    assert res.ok is True
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


def test_the_album_reaches_the_kid_safe_guard(spotify, transport):
    # Spotty is the only feed that hands over an album name, and the guard
    # checks every name field of a resolved item — so a blocked album must
    # block its tracks even when neither title nor artist is on the list.
    import actions
    from guard import Guard

    transport.responses["spotty"] = spotty_feed()
    res = actions.play_song(spotify, "Money For Nothing",
                            guard=Guard(restricted=True,
                                        blocklist=["The Best Of Dire Straits"]))
    assert res.ok is False
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


# -- the shortlist, and the names read aloud ------------------------------------

def test_the_category_links_do_not_eat_the_shortlist(spotify, transport):
    # The links are the first rows and they count against the quantity asked
    # for: a plain count of 20 came back as 14 tracks, a third smaller than the
    # shortlist TIDAL and Qobuz get for the same request.
    many = ([{"name": f"Cat {n}", "isaudio": 0, "hasitems": 1, "id": f"c.{n}"}
             for n in range(6)]
            + [{"name": f"Song {n} by A from B", "isaudio": 1, "hasitems": 1,
                "id": f"t.{n}"} for n in range(30)])
    inner = spotty_feed(children=many)

    def handler(cmd):
        # Honour the quantity the client asked for — LMS does, and that is the
        # whole point here: without headroom the six links are six fewer tracks.
        res = inner(cmd)
        loop = res.get("loop_loop")
        if loop is not None and len(cmd) > 3 and str(cmd[3]).isdigit():
            return {"loop_loop": loop[:int(cmd[3])]}
        return res

    transport.responses["spotty"] = handler
    assert len(spotify.search_tracks("x", count=20)) == 20


def test_album_listings_are_stripped_of_the_feeds_packaging(spotify,
                                                            transport):
    # Verbatim from the live plugin. Nothing plays by these strings, but they
    # are read back aloud, and «Metto "1. So Far Away - Remastered 1996 by Dire
    # Straits from Brothers In Arms"» is not a sentence to say to somebody.
    def handler(cmd):
        params = cmd[2:]
        item_id = next((p[len("item_id:"):] for p in params
                        if p.startswith("item_id:")), None)
        if item_id is None:
            return {"loop_loop": [{"id": "1", "name": "Search", "type": "link",
                                   "hasitems": 1}]}
        if item_id == "1":
            return {"loop_loop": [{"id": "1.0", "name": "New Search",
                                   "type": "search", "hasitems": 1}]}
        if item_id == "1.0":
            return {"loop_loop": [
                {"name": "Albums", "isaudio": 0, "hasitems": 1, "id": "1.0_x.1"}]}
        if item_id == "1.0_x.1":
            return {"loop_loop": [
                {"id": "alb", "hasitems": 1,
                 "name": "Brothers In Arms (Remastered 1996) by Dire Straits"}]}
        return {"loop_loop": [
            {"isaudio": 1, "url": "spotify://track:1",
             "name": "1. So Far Away - Remastered 1996 by Dire Straits "
                     "from Brothers In Arms"}]}

    transport.responses["spotty"] = handler
    assert spotify.album_candidates("brothers in arms") == [
        {"id": "alb", "title": "Brothers In Arms (Remastered 1996)"}]
    assert spotify.album_tracks("brothers in arms")["tracks"] == [
        {"url": "spotify://track:1", "title": "So Far Away - Remastered 1996"}]


# -- the refusal, on every path that resolves to a single first result ----------

@pytest.mark.parametrize("call,kind", [
    ("play_album", "album"), ("play_playlist", "playlist"),
    ("play_artist", "artist"),
])
def test_nothing_is_started_for_a_query_nothing_matches(spotify, transport,
                                                        call, kind):
    # The song path refused from the start; these three did not, and all three
    # are reachable on Spotify (localvoice/intents.py dispatches them through
    # for_service). Verified against the live server: «zzzzqqqxyzzy» returns 20
    # albums, 20 artists and 20 playlists, so each of them acted.
    import actions

    def handler(cmd):
        params = cmd[2:]
        item_id = next((p[len("item_id:"):] for p in params
                        if p.startswith("item_id:")), None)
        if item_id is None:
            return {"loop_loop": [{"id": "1", "name": "Search", "type": "link",
                                   "hasitems": 1}]}
        if item_id == "1":
            return {"loop_loop": [{"id": "1.0", "name": "New Search",
                                   "type": "search", "hasitems": 1}]}
        if item_id == "1.0":
            return {"loop_loop": [
                {"name": "Artists", "isaudio": 0, "hasitems": 1, "id": "c.0"},
                {"name": "Albums", "isaudio": 0, "hasitems": 1, "id": "c.1"},
                {"name": "Playlists", "isaudio": 0, "hasitems": 1, "id": "c.2"},
            ]}
        # every category answers with something irrelevant, as Spotify does
        return {"loop_loop": [{"id": "irrelevant", "hasitems": 1,
                               "name": "Il pulcino Pio"}]}

    transport.responses["spotty"] = handler
    res = getattr(actions, call)(spotify, "zzzzqqqxyzzy")
    assert res.ok is False, f"{call} acted on a query nothing matched"
    assert not any(c[:3] == ["spotty", "playlist", "play"]
                   for c in transport.commands()), "something was started"
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_the_other_services_still_act_on_their_first_result(lms, transport,
                                                            make_feed):
    # The same four paths must be untouched for TIDAL and Qobuz, whose empty
    # answers are what make the first result meaningful.
    import actions

    transport.responses["tidal"] = make_feed(
        search_node="7", categories={"Albums": "A"},
        items={"A": [{"id": "alb", "hasitems": 1, "name": "Some Other Album"}]})
    res = actions.play_album(lms, "a title that matches nothing")
    assert res.ok is True
    assert ["tidal", "playlist", "play", "item_id:alb"] in transport.commands()


# -- an artist, whose tracks carry an id and no url -----------------------------
# The same difference as the search results, one node deeper — and the artist
# path did not know about it. ``artist_tracks`` dropped every row for want of a
# url, so a Spotify artist came back "non riesco a riprodurre" while the songs
# were sitting right there.
ARTIST_TRACK_URLS = {"tt.1": "spotify://track:aaaaaaaaaaaaaaaaaaaaa1",
                     "tt.2": "spotify://track:aaaaaaaaaaaaaaaaaaaaa2"}


def spotty_artist_feed(track_urls=None):
    urls = ARTIST_TRACK_URLS if track_urls is None else track_urls

    def handler(cmd):
        params = cmd[2:]
        item_id = next((p[len("item_id:"):] for p in params
                        if p.startswith("item_id:")), None)
        if item_id is None:
            return {"loop_loop": [{"id": "1", "name": "Search",
                                   "type": "link", "hasitems": 1}]}
        if item_id == "1":
            return {"loop_loop": [{"id": "1.0", "name": "New Search",
                                   "type": "search", "hasitems": 1}]}
        if item_id == "1.0":                       # search node -> categories
            return {"loop_loop": [{"id": "cat.artists", "name": "Artists",
                                   "hasitems": 1}]}
        if item_id == "cat.artists":
            return {"loop_loop": [{"id": "ar.1", "name": "Pink Floyd",
                                   "hasitems": 1}]}
        if item_id == "ar.1":                      # the artist's children
            return {"loop_loop": [
                {"id": "alb", "name": "Albums", "hasitems": 1},
                {"id": "tt", "name": "Top Tracks", "hasitems": 1},
            ]}
        if item_id == "tt":                        # ...no url on any row
            return {"loop_loop": [
                {"id": "tt.1", "name": "Money", "isaudio": 1, "hasitems": 1},
                {"id": "tt.2", "name": "Time", "isaudio": 1, "hasitems": 1},
            ]}
        url = urls.get(item_id)                    # the track node's audio child
        return {"item_loop": ([{"type": "audio", "text": url,
                                "presetParams": {"favorites_url": url}}]
                              if url else [])}

    return handler


def test_an_artists_tracks_survive_having_no_url(spotify, transport):
    transport.responses["spotty"] = spotty_artist_feed()
    tracks = spotify.artist_tracks({"id": "ar.1"})
    assert [t["title"] for t in tracks] == ["Money", "Time"]
    assert [t["item_id"] for t in tracks] == ["tt.1", "tt.2"]
    assert not any("url" in t for t in tracks)


def test_playing_an_artist_resolves_each_url_only_as_it_queues_it(spotify,
                                                                  transport):
    import actions
    transport.responses["spotty"] = spotty_artist_feed()
    assert actions.play_artist(spotify, "Pink Floyd") == \
        "Riproduco la musica di Pink Floyd."
    cmds = transport.commands()
    assert ["playlist", "play", ARTIST_TRACK_URLS["tt.1"]] in cmds
    assert ["playlist", "add", ARTIST_TRACK_URLS["tt.2"]] in cmds


def test_a_track_whose_url_cannot_be_resolved_is_skipped_not_fatal(spotify,
                                                                   transport):
    # One unresolvable row must not take the other one's music down with it.
    transport.responses["spotty"] = spotty_artist_feed(
        {"tt.2": ARTIST_TRACK_URLS["tt.2"]})
    spotify.play_tracks(spotify.artist_tracks({"id": "ar.1"}))
    assert ["playlist", "play", ARTIST_TRACK_URLS["tt.2"]] in transport.commands()
    assert not any(cmd[:2] == ["playlist", "add"] for cmd in transport.commands())
