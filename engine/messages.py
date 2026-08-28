"""Message catalog — every user-facing speech string, keyed by id.

The engine and the frontends reference message *keys*; the wording lives in
``engine/catalogs/``, one module per language, and this module is only what
selects between them. Adding a language is adding a catalog module there (and
a pattern pack in ``localvoice/lang/``): nothing here has to change.

Templates use :meth:`str.format` named fields; :func:`msg` formats them.
"""

from __future__ import annotations

from catalogs import CATALOGS

# The shipped catalogs by name, for callers and tests that want one directly.
# ``CATALOGS`` is the registry; these are conveniences over it.
IT = CATALOGS["it"]
EN = CATALOGS["en"]
DE = CATALOGS["de"]

DEFAULT_LANG = "it"

# Per-request language, so concurrent web requests in different languages don't
# step on each other (contextvars are async- and thread-safe per execution
# context; our HTTP server is thread-per-request).
import contextvars as _contextvars

_current_lang = _contextvars.ContextVar("vivavoce_lang", default=DEFAULT_LANG)


def set_lang(lang: str) -> None:
    """Select the reply language for the current request; unsupported values
    fall back to the default (Italian)."""
    _current_lang.set(lang if lang in CATALOGS else DEFAULT_LANG)


def get_lang() -> str:
    return _current_lang.get()


def msg(key: str, *, lang: str = None, **kwargs) -> str:
    """The message for ``key`` in ``lang`` (default: the per-request language
    set via :func:`set_lang`, else Italian), formatted with ``kwargs``. A
    missing key raises ``KeyError`` — a wrong key is a bug, not a runtime
    condition to paper over."""
    return CATALOGS[lang or _current_lang.get()][key].format(**kwargs)
