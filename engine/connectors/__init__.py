"""Per-language connectors, discovered the way ``engine/catalogs/`` discovers
its message catalogs and ``localvoice/lang/`` its pattern packs.

A connector is the word that joins the parts of a spoken request: the filler
in front of a title («la canzone X»), the phrase that introduces an album
(«dall'album X»), the one that introduces an artist («di X», "by X"), and the
tails that are never an artist name however much they look like one.

They were one pile, matched by every language at once, until French arrived.
French's artist connector is «de», ``parse_song_query`` scans right to left,
and so a shared «de» turned «la canzone di Marinella di De André» into a
search for a singer called «André». French got a module of its own and the
other three stayed in the pile — which left the package saying two things at
once, and left «von» splitting an Italian request. Now each language answers
for its own words and for nobody else's: a module here declares ``CODE`` and
the four tables, and what it declares is what that language matches. Nothing
is shared, because "shared" is the bug French found.

The price is a request phrased in one language and heard by a recogniser set
to another: «Comfortably Numb von Pink Floyd» under Italian is one title now,
not a title and an artist. The runtime is the reason that is affordable —
``Router.handle`` calls ``set_lang`` before anything parses, so the language
in flight is the language of the phrase far more often than not.

A module without ``CODE`` is invisible here, so a helper can sit in the
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

from messages import DEFAULT_LANG

FIELDS = ("LEAD_FILLER", "ALBUM_SEP", "ARTIST_SEP", "NOT_AN_ARTIST")

# What a language that declares no such connector compiles to. It has to be a
# pattern that can never match anything: an empty group ``(?:)`` matches the
# empty string at every position, which would split every title in two.
_NEVER = r"(?!)"

#: What ``matching.parse_song_query`` needs to split one request, compiled.
ConnectorSet = namedtuple(
    "ConnectorSet", "lead_filler album_sep artist_sep not_an_artist")


def _build(mod) -> ConnectorSet:
    """Compile what ``mod`` declares, and only what ``mod`` declares."""
    def alts(name):
        return getattr(mod, name, None) or _NEVER

    return ConnectorSet(
        lead_filler=re.compile(rf"^(?:{alts('LEAD_FILLER')})\s+", re.IGNORECASE),
        album_sep=re.compile(rf"\b(?:{alts('ALBUM_SEP')})\b", re.IGNORECASE),
        # No trailing \s+ out here: each alternative carries its own, because
        # French elision does not leave one behind («d'Édith Piaf»).
        artist_sep=re.compile(rf"\b(?:{alts('ARTIST_SEP')})", re.IGNORECASE),
        not_an_artist=set(getattr(mod, "NOT_AN_ARTIST", ()) or ()),
    )


CONNECTORS = {}
for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if not hasattr(_mod, "CODE"):
        continue  # a helper, not a language
    if not any(hasattr(_mod, _f) for _f in FIELDS):
        raise ImportError(
            f"connectors/{_info.name}.py declares CODE but none of {FIELDS}")
    CONNECTORS[_mod.CODE] = _build(_mod)

#: The default language's set, for a code this package has never heard of —
#: the same fallback ``messages.set_lang`` makes for an unknown language, so
#: the words and the wording agree about what "unknown" means. A KeyError here
#: is the right failure: the default language has to have connectors.
DEFAULT = CONNECTORS[DEFAULT_LANG]


def for_lang(code) -> ConnectorSet:
    """The connectors to split a request said in ``code`` — the default
    language's when this package has never heard of it."""
    return CONNECTORS.get(code, DEFAULT)
