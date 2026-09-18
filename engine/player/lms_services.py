"""Which streaming services an LMS can be aimed at, and how their URIs read.

A table and pure functions: no client, no round trip, nothing here can fail.
It sits at the bottom of the LMS side so that the three mixins above it —
``lms_feed``, ``lms_library`` and ``lms_transport`` — can all read it without
importing each other or the client that composes them.

Split out of ``engine/lms.py`` when that file was 1317 lines and the only one
exempt from this repo's own 400-line rule (``tests/test_packaging.py``).
Nothing moved changed; ``lms.py`` re-exports every name that was public.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


def _uri_re(schemes: Tuple[str, ...]) -> "re.Pattern":
    """URI regex for a service's scheme(s): entity forms (``album:ID`` etc.) or
    the bare-track form ``<digits>.<ext>`` (e.g. ``tidal://55391466.flc``)."""
    alt = "|".join(re.escape(s) for s in schemes)
    return re.compile(
        rf"(?:{alt})://(?:(?:track|album|artist|playlist|mix):[^\s\"']+|\d+\.[A-Za-z0-9]+)",
        re.IGNORECASE,
    )


@dataclass(frozen=True)
class ServiceSpec:
    """Everything service-specific about an LMS streaming app feed."""

    name: str                    # registry key as spoken: "tidal" / "spotify"
    tag: str                     # CLI tag: cmd[0] of ["<tag>","items",...]
                                 # (not always the name: "spotify" -> "spotty")
    schemes: Tuple[str, ...]     # URL scheme(s) the plugin's tracks use
    category_aliases: Dict[str, tuple]  # canonical -> names the plugin may show
    artist_children: Tuple[str, ...]    # playable child nodes under an artist
    # How the name is spelled when a reply says it out loud: "qobuz" is a
    # config key, «Qobuz» is what the user hears. It lives here because the
    # registry is where a service is described, and two modules now need it —
    # the source tag on a play confirmation and the engine's own "that service
    # is not connected".
    label: str = ""
    # Some plugins (Qobuz) nest the search node one level down: home shows a
    # plain "Search" link whose CHILD is the ``type == "search"`` node. These
    # are the (lowercased) home-menu names worth entering to look for it.
    search_parents: Tuple[str, ...] = ()
    # Display noise the plugin appends to track titles (e.g. Qobuz's
    # " (Hi-Res)" quality tag and " [E]" parental marker), stripped before
    # scoring/confirmation so «Comfortably Numb» matches exactly.
    title_noise_re: Any = None
    # When the menu-mode text's 2nd line is "Artist<sep>Album" (Qobuz) rather
    # than just the artist (TIDAL), split on this to keep the artist part.
    artist_line_sep: Optional[str] = None
    # Spotty does not put songs in a category. Its search node answers with the
    # category links (Artists/Albums/Playlists/...) and the matching *tracks as
    # their siblings*, flagged ``isaudio``, with title/artist/album packed into
    # one ``name`` and no url at all. Two flags describe that shape:
    #   tracks_inline   read tracks from the search node's own children rather
    #                   than from a "Songs" category, which does not exist
    #   track_name_re   splits that one name; groups: title, artist, album
    tracks_inline: bool = False
    track_name_re: Any = None
    # The same packaging on an album row, which carries no " from " part:
    # "Brothers In Arms (Remastered 1996) by Dire Straits".
    album_name_re: Any = None
    # An artist's child nodes are rendered in the LMS UI language, exactly like
    # the search categories above — and unlike them, they used to be matched
    # exactly and case-sensitively against the English names in
    # ``artist_children``, so a plugin showing «Brani» made every artist
    # unplayable and said "non posso riprodurre" about a catalogue that had the
    # music. Canonical name -> the spellings a plugin may show; a canonical
    # name that is also a search category falls back to ``category_aliases``,
    # since it is the same word in the same language. Matching is
    # case-insensitive either way.
    #
    # Deliberately empty for the names that are NOT also categories ("Top
    # Tracks", "Artist Mix"): their localized spellings have not been read off
    # a live plugin, and guessing them here would be indistinguishable from
    # having verified them. ``tools/probe_lms.py`` prints the verbatim names —
    # that is where the entries come from.
    artist_child_aliases: Dict[str, tuple] = field(default_factory=dict)
    # Whether "no title matched, so play the top result" is a safe fallback.
    # It is for a search that answers *nothing* when nothing matches, which is
    # what TIDAL and Qobuz do — there, the top result being returned at all is
    # itself evidence. Spotify's search always answers: «zzzzqqqxyzzy» comes
    # back with fourteen tracks, and trusting the ranking there means playing a
    # song nobody asked for, in silence, which is the one thing this product
    # promises not to do. Off for such a service: say it was not found.
    trust_ranking: bool = True
    uri_re: Any = field(init=False, default=None, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "uri_re", _uri_re(self.schemes))


# How many non-track rows a ``tracks_inline`` feed puts before the tracks.
# Six on Spotty (Artists, Albums, Playlists, Podcasts, Podcast Episodes,
# Users); asking for a few more than that costs nothing and guards against the
# plugin adding a seventh.
_INLINE_HEADROOM = 10

# "1. So Far Away ..." — the position Spotty prefixes to album tracks.
_TRACK_NUMBER_RE = re.compile(r"^\d{1,3}\.\s+")

SERVICES: Dict[str, ServiceSpec] = {
    # Verified against a live LMS/Daphile (see module docstring).
    "tidal": ServiceSpec(
        name="tidal",
        tag="tidal",
        label="TIDAL",
        schemes=("tidal", "wimp"),  # wimp:// is the legacy TIDAL scheme
        category_aliases={
            "Songs": ("Songs", "Brani", "Canzoni", "Tracce"),
            "Albums": ("Albums", "Album"),
            "Artists": ("Artists", "Artisti"),
            "Playlists": ("Playlists", "Playlist"),
        },
        artist_children=("Top Tracks", "Artist Mix"),
    ),
    # Verified live against LMS 9.0.3 + plugin-Qobuz 3.7.0 (2026-07-14):
    # categories come back as Releases/Artists/Songs/Playlists, the search
    # node is nested under a "Search" link, tracks are ``qobuz://<id>.flac``,
    # titles carry " (Hi-Res)" and the artist line is "Artist - Album".
    "qobuz": ServiceSpec(
        name="qobuz",
        tag="qobuz",
        label="Qobuz",
        schemes=("qobuz",),
        category_aliases={
            "Songs": ("Songs", "Tracks", "Brani", "Canzoni", "Tracce"),
            "Albums": ("Releases", "Albums", "Album"),
            "Artists": ("Artists", "Artisti"),
            "Playlists": ("Playlists", "Playlist"),
        },
        artist_children=("Songs", "Top Tracks"),
        search_parents=("search", "cerca", "ricerca"),
        title_noise_re=re.compile(r"(?:\s*\(Hi-Res\)|\s*\[E\])+\s*$", re.IGNORECASE),
        artist_line_sep=" - ",
    ),
    # Spotify, through the Spotty plugin (``cmd`` is "spotty", not "spotify" —
    # the registry key is what a person says, the tag is what LMS answers to).
    #
    # Verified live against LMS 9.0.3 + Spotty (2026-08-28), and it turned out
    # not to follow the pattern the other two share. Three differences, each
    # read off the wire rather than assumed:
    #
    #  1. **there is no Songs category.** The search node answers with the
    #     category links — Artists, Albums, Playlists, Podcasts, Podcast
    #     Episodes, Users — and then the matching tracks as their *siblings*;
    #  2. **a track carries no url.** It is `{"id", "name", "isaudio": 1,
    #     "hasitems": 1}` and nothing else. The url lives one level down, as the
    #     name of its single ``type == "audio"`` child:
    #     ``spotify://track:01Txvu3dNthhldq8oR0Pae``. See ``track_url``;
    #  3. **title, artist and album are one string**, "T by A from B", where the
    #     other two feeds give a separate ``text`` line.
    #
    # It also needs Spotify Premium, which is not a detail: Spotty plays through
    # Spotify Connect, so on a free account its whole menu is one "credentials
    # missing" notice and every search here returns nothing.
    "spotify": ServiceSpec(
        name="spotify",
        tag="spotty",
        label="Spotify",
        schemes=("spotify",),
        # No "Songs": that is the whole point of ``tracks_inline`` below. The
        # four that are here were read off a live search.
        category_aliases={
            "Albums": ("Albums", "Album"),
            "Artists": ("Artists", "Artisti"),
            "Playlists": ("Playlists", "Playlist"),
            "Podcasts": ("Podcasts", "Podcast"),
        },
        # Read off a live artist node, whose children are: Albums, Singles &
        # EPs, Compilations, Top Tracks, Artist Radio, Related Artists, Follow
        # artist. Only the one we can play is listed — a speculative entry in
        # here would cost the table the thing that makes it worth reading.
        artist_children=("Top Tracks",),
        search_parents=("search", "cerca", "ricerca"),
        tracks_inline=True,
        trust_ranking=False,
        # "Money For Nothing by Dire Straits from The Best Of Dire Straits".
        # The title group is greedy on purpose: an artist almost never contains
        # " by " while a title routinely does, so «Killed by Death by Motorhead
        # from ...» has to give the last " by " to the split, not the first.
        track_name_re=re.compile(r"^(?P<title>.+) by (?P<artist>.+?) from "
                                 r"(?P<album>.+)$"),
        album_name_re=re.compile(r"^(?P<title>.+) by (?P<artist>.+)$"),
    ),
}

# All registered schemes, for service-independent URI classification.
_ANY_SCHEME = "|".join(
    re.escape(s) for spec in SERVICES.values() for s in spec.schemes
)

# Backward-compatible alias (the TIDAL-only regex predates ServiceSpec).
_TIDAL_URI = SERVICES["tidal"].uri_re

# Scheme -> registry name, for the two places LMS names a service in a library
# row: the track url (``tidal://322955652.flc``) and the ``extid`` of a row
# imported from an online library (``tidal:album:322955651``, and for an artist
# a comma-separated list, ``qobuz:artist:6505891,tidal:artist:15694955``). Both
# spell the service the same way the registry does, which is why one map reads
# both.
_SERVICE_BY_SCHEME = {scheme: name
                      for name, spec in SERVICES.items()
                      for scheme in spec.schemes}


def service_of(uri: Optional[str]) -> Optional[str]:
    """The registry name behind a library row's url or ``extid``; None for a
    file on a disk, which needs nobody's permission to play."""
    if not uri:
        return None
    return _SERVICE_BY_SCHEME.get(str(uri).split(":", 1)[0].strip().lower())


def _with_extid(cand: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """``cand`` plus the row's ``extid``, and only when it has one — which is
    the same thing as saying the row was imported from an online library. A
    key that is present and empty would say something else, and every caller
    that compares whole candidate dicts would have to learn about it."""
    if row.get("extid"):
        cand["extid"] = row["extid"]
    return cand


def _as_int(value: Any) -> int:
    """``playlist_cur_index`` and friends, which LMS sends as strings."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def find_uri(obj: Any, pattern: "re.Pattern") -> Optional[str]:
    """Recursively search a (possibly nested) OPML item for the first URI
    matching ``pattern``."""
    if isinstance(obj, str):
        match = pattern.search(obj)
        return match.group(0) if match else None
    if isinstance(obj, dict):
        for value in obj.values():
            uri = find_uri(value, pattern)
            if uri:
                return uri
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            uri = find_uri(value, pattern)
            if uri:
                return uri
    return None


def find_tidal_uri(obj: Any) -> Optional[str]:
    """Recursively search a (possibly nested) OPML item for the first TIDAL URI."""
    return find_uri(obj, _TIDAL_URI)


def _split_text(text: Any) -> tuple:
    """Split a menu item's ``text`` ('Title\\nArtist') into (title, artist)."""
    if not text:
        return None, None
    lines = [p.strip() for p in str(text).split("\n") if p.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    return (lines[0] if lines else None), None


def uri_kind(uri: str) -> Optional[str]:
    """Classify a streaming URI (any registered service) as
    track/album/artist/playlist/mix."""
    match = re.match(
        rf"(?:{_ANY_SCHEME})://(track|album|artist|playlist|mix):", uri, re.IGNORECASE
    )
    if match:
        return match.group(1).lower()
    if re.match(rf"(?:{_ANY_SCHEME})://\d+\.[A-Za-z0-9]+$", uri, re.IGNORECASE):
        return "track"
    return None

