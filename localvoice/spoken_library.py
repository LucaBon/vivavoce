"""``--library``: a catalogue of audiobooks beside the music system.

The startup half of :mod:`player.composite`, split out of ``server.py`` for
the reason ``cli.py`` was: what to make of three options is its own subject,
and ``server.py`` lives near the 400-line ceiling.

Two kinds of trouble, told apart on purpose. Options that cannot work — a
name nobody registered, a URL or a key missing — stop the app at startup,
like ``--services`` does, because they are typos and the reply should say
what could have been typed. A catalogue that does not answer *today* does
not stop anything: the music has nothing to do with the books, and refusing
to start the voice assistant because the bookshelf server is rebooting would
be calling an outage a misspelling.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Callable, Optional, Tuple

from player import PlayerError
from player import registry as player_registry
from player.composite import Composite


def _loopback(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host == "localhost" or host.startswith("127.") or host == "::1"


def open_library(args: Any, say: Callable[[str], None] = print
                 ) -> Tuple[Optional[Composite], str]:
    """``(composite, complaint)`` for the ``--library*`` options.

    ``(None, "")`` when no library was asked for — and then nothing is built,
    probed or printed, which is the whole promise to a household without
    books. A non-empty complaint means the options cannot work and the app
    should say so and stop.
    """
    name = (args.library or "").strip().lower()
    url = (args.library_url or "").strip()
    token = (args.library_token or "").strip()
    available = ", ".join(sorted(player_registry.LIBRARIES))
    if not name:
        if url or token:
            return None, (f"--library-url/--library-token senza --library: "
                          f"quale catalogo? (disponibili: {available})")
        return None, ""
    try:
        library = player_registry.get_library(name)
    except ValueError:
        return None, f"--library non valido: {name!r} (disponibili: {available})"
    if "://" not in url:
        return None, (f"{library.label}: indica dove trovarlo con "
                      f"--library-url, es. http://192.168.1.50:13378")
    if not token:
        return None, (f"{library.label}: serve una chiave API "
                      f"(--library-token), senza non mostra nessun libro")
    if _loopback(url):
        # Not refused: the hi-fi may well run on this same machine. But the
        # files are fetched by the hi-fi, not by this app, and on any other
        # box «localhost» is the hi-fi itself.
        say(f"Attenzione: {url} è un indirizzo locale. I file dei libri li "
            f"scarica l'impianto, non questo PC: se l'impianto è un'altra "
            f"macchina, usa l'IP di rete.")
    composite = Composite(library.build(url, token=token),
                          library.capabilities, library.label)
    try:
        shelves = library.probe(url, token=token)
    except PlayerError as exc:
        say(f"{library.label} non risponde ({exc}): gli audiolibri restano "
            f"irraggiungibili finché non torna, la musica no.")
        return composite, ""
    if shelves:
        names = ", ".join(s["name"] for s in shelves if s.get("name"))
        noun = "libreria" if len(shelves) == 1 else "librerie"
        say(f"{library.label}: {len(shelves)} {noun} di libri"
            + (f" ({names})" if names else ""))
    else:
        say(f"{library.label} risponde, ma con questa chiave non vede nessuna "
            f"libreria di libri.")
    return composite, ""
