"""Catalog registry: one module per language, discovered by itself.

``messages.py`` asks this package which catalogs exist; each one is a module
declaring ``CODE`` (the language code the client sends) and ``MESSAGES`` (the
message-id -> wording dict). Adding a language is dropping a file in here —
plus its pattern pack in ``localvoice/lang/`` and a test suite modeled on
``tests/test_english.py``. Nothing else changes.

The split exists because the catalogs are a *list*, not a program: three
languages of prose had grown ``messages.py`` past the size guard in
``tests/test_packaging.py``, and every further language would push it further
while the machinery beside them — twenty lines of contextvar — never moves.

Discovery is deliberate about failure, like ``localvoice/lang``: a module
missing part of the contract breaks the import loudly at startup, not a
lookup quietly at runtime.
"""

from __future__ import annotations

import importlib
import pkgutil

#: ``{"it": {...}, "en": {...}, "de": {...}}``
CATALOGS = {}

for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if not hasattr(_mod, "CODE"):
        continue  # helpers, not catalogs
    if not hasattr(_mod, "MESSAGES"):
        raise ImportError(
            f"message catalog {__name__}.{_info.name} is missing MESSAGES")
    CATALOGS[_mod.CODE] = _mod.MESSAGES
