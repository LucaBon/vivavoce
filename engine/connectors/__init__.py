"""Per-language connectors, discovered the way ``engine/catalogs/`` discovers
its message catalogs and ``localvoice/lang/`` its pattern packs.

A module in this package declares ``CODE`` and any of ``LEAD_FILLER``,
``ALBUM_SEP``, ``ARTIST_SEP`` (alternation fragments) and ``NOT_AN_ARTIST``
(a set of normalized words). Whatever it declares is added to the shared set
in ``shared.py`` — for that language and no other, which is the whole point:
see that module for what French made impossible to keep sharing.

A module without ``CODE`` is invisible here, so ``shared.py`` can sit in the
package without being mistaken for a language — the same way ``base.py`` does
in ``localvoice/lang/``. A module *with* ``CODE`` and none of the four names
raises: it declares a language and then says nothing about it, which is a
typo rather than an intention.

The composition happens once, at import, for every registered language. A
request pays a dict lookup.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections import namedtuple

from . import shared

FIELDS = ("LEAD_FILLER", "ALBUM_SEP", "ARTIST_SEP", "NOT_AN_ARTIST")

#: What ``matching.parse_song_query`` needs to split one request, compiled.
ConnectorSet = namedtuple(
    "ConnectorSet", "lead_filler album_sep artist_sep not_an_artist")


def _build(mod=None) -> ConnectorSet:
    """The shared connectors, widened by ``mod``'s if it declares any."""
    def alts(name):
        extra = getattr(mod, name, None) if mod is not None else None
        core = getattr(shared, name)
        return f"{core}|{extra}" if extra else core

    return ConnectorSet(
        lead_filler=re.compile(rf"^(?:{alts('LEAD_FILLER')})\s+", re.IGNORECASE),
        album_sep=re.compile(rf"\b(?:{alts('ALBUM_SEP')})\b", re.IGNORECASE),
        # No trailing \s+ out here: each alternative carries its own, because
        # French elision does not leave one behind («d'Édith Piaf»).
        artist_sep=re.compile(rf"\b(?:{alts('ARTIST_SEP')})", re.IGNORECASE),
        not_an_artist=shared.NOT_AN_ARTIST | set(
            getattr(mod, "NOT_AN_ARTIST", ()) or ()),
    )


#: The set for a language that adds nothing — and the fallback for one this
#: package has never heard of.
SHARED = _build()

CONNECTORS = {}
for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if not hasattr(_mod, "CODE"):
        continue  # shared.py: the core, not a language
    if not any(hasattr(_mod, _f) for _f in FIELDS):
        raise ImportError(
            f"connectors/{_info.name}.py declares CODE but none of {FIELDS}")
    CONNECTORS[_mod.CODE] = _build(_mod)


def for_lang(code) -> ConnectorSet:
    """The connectors to split a request said in ``code`` — the shared set
    when that language adds nothing of its own."""
    return CONNECTORS.get(code, SHARED)
