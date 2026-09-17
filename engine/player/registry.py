"""Backend registry: one module per music system, discovered by itself.

A backend module declares ``BACKEND``, a :class:`Backend` saying what it is
called, what it can do, and how to build a client for it. A catalogue that
plays nothing declares ``SPOKEN_LIBRARY`` instead (:class:`Library`), and is
found by the same scan. Adding a music system is dropping a file in this
package and writing its test suite. Nothing in ``engine/`` or ``localvoice/``
learns its name.

Discovery is deliberate about failure, like ``engine/catalogs`` and
``localvoice/lang``: a module that declares ``BACKEND`` and then gets the
contract wrong breaks the import loudly at startup, rather than at the moment
somebody speaks to it.

Importing this module imports every backend, and a backend imports its client.
That is why ``player/__init__.py`` does **not** import it: the engine reaches
for :class:`~player.errors.PlayerError` on nearly every path and has no
business dragging a music-server client in behind it. Whoever actually needs
to *build* a client asks for this module by name.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .protocols import Capabilities

#: This package's directory. ``registry`` is a module inside the package,
#: so it has no ``__path__`` of its own to hand to pkgutil.
_HERE = os.path.dirname(os.path.abspath(__file__))


@dataclass(frozen=True)
class Backend:
    """One music system: what to call it, what it can do, how to reach it."""

    #: Registry key, as typed after ``--backend``. Lowercase, no spaces.
    name: str
    #: How the name is spelled when a reply or a log line says it out loud.
    label: str
    #: What this system can do. The engine asks before it offers — see
    #: :class:`~player.protocols.Capabilities`.
    capabilities: Capabilities
    #: ``(url, player_id, *, token=None, timeout=...) -> client``.
    build: Callable[..., Any]
    #: ``(url, *, token=None, timeout=...) -> [{"playerid", "name"}, ...]``.
    #: Used by the setup page to answer "is it there, and what can it play
    #: through?" before a player has been chosen. Raises like the client does.
    probe: Callable[..., List[Dict[str, Any]]]
    #: The port this system answers on, used to complete an address somebody
    #: typed as a bare IP. Getting it wrong is silent — the address looks
    #: right and nothing ever replies — which is why it is declared rather
    #: than assumed.
    default_port: int = 9000
    #: ``(*, on_progress=None) -> url or None``: find this system on the LAN.
    #: ``None`` for a system that cannot be found without being told where it
    #: is — which is a fact about the system, not a missing feature.
    discover: Optional[Callable[..., Optional[str]]] = None


@dataclass(frozen=True)
class Library:
    """A catalogue that plays nothing, heard through a backend's speakers.

    Declared as ``SPOKEN_LIBRARY`` rather than ``BACKEND``, and the difference
    is the whole of :class:`~player.protocols.SpokenLibrary`: a backend is a music
    system with players, so it can be what ``--backend`` points at, and it
    owes the transport controls. A library has no player to aim, one address
    and one token of its own, and is named by ``--library`` alongside
    whichever backend is playing. Squeezing it into :class:`Backend` would
    have meant a ``build`` that takes a player id it cannot use and a
    ``probe`` that answers "which players?" with a list of bookshelves.
    """

    #: Registry key, as typed after ``--library``.
    name: str
    #: How it is said out loud.
    label: str
    #: What it can do. Always ``streamable``: a library that could not say
    #: where its files are would have nothing to offer.
    capabilities: Capabilities
    #: ``(url, *, token=None, timeout=...) -> client``. Dials nothing, like a
    #: backend's.
    build: Callable[..., Any]
    #: ``(url, *, token=None, timeout=...) -> [{"id", "name"}, ...]``: the
    #: collections this catalogue would search. Raises like the client does.
    probe: Callable[..., List[Dict[str, Any]]]


def _load() -> Tuple[Dict[str, Backend], Dict[str, Library]]:
    backends: Dict[str, Backend] = {}
    libraries: Dict[str, Library] = {}
    package = __name__.rsplit(".", 1)[0]
    for info in sorted(pkgutil.iter_modules([_HERE]), key=lambda m: m.name):
        module = importlib.import_module(f"{package}.{info.name}")
        where = f"{package}.{info.name}"
        _admit(getattr(module, "BACKEND", None), Backend, backends, where)
        _admit(getattr(module, "SPOKEN_LIBRARY", None), Library, libraries,
               where)
    # One namespace for both: a name that meant a music system after --backend
    # and a bookshelf after --library would make every log line that says it
    # ambiguous.
    shared = sorted(set(backends) & set(libraries))
    if shared:
        raise ImportError(
            f"{', '.join(shared)} is both a backend and a library")
    return backends, libraries


def _admit(declared: Any, kind: type, found: Dict[str, Any],
           where: str) -> None:
    """File one ``BACKEND`` or ``SPOKEN_LIBRARY`` declaration, loudly if it
    is wrong."""
    if declared is None:
        return  # protocols, errors, resilience: machinery, not declarations
    label = "BACKEND" if kind is Backend else "SPOKEN_LIBRARY"
    if not isinstance(declared, kind):
        raise ImportError(
            f"{where} declares {label} but it is not a {kind.__name__} "
            f"(got {type(declared).__name__})")
    if not declared.name:
        raise ImportError(f"{where} declares a nameless {label}")
    if declared.name in found:
        raise ImportError(
            f"two {label} declarations are both called "
            f"{declared.name!r}: {where} and one imported before it")
    found[declared.name] = declared


#: ``{"lms": Backend(...), ...}`` and ``{"audiobookshelf": Library(...)}``,
#: in name order.
BACKENDS, LIBRARIES = _load()


def get(name: str) -> Backend:
    """The backend called ``name``, or a ValueError naming the ones that exist.

    Mirrors how ``--services`` validates against ``lms.SERVICES``: an
    unrecognised name is a typo at startup, and the reply should say what
    could have been typed instead.
    """
    try:
        return BACKENDS[name]
    except KeyError:
        raise ValueError(
            f"unknown backend {name!r} "
            f"(available: {', '.join(sorted(BACKENDS))})") from None


def get_library(name: str) -> Library:
    """The library called ``name``, or a ValueError naming those that exist."""
    try:
        return LIBRARIES[name]
    except KeyError:
        raise ValueError(
            f"unknown library {name!r} "
            f"(available: {', '.join(sorted(LIBRARIES))})") from None
