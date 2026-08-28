"""Language registry: one module per spoken language, discovered by itself.

The router asks this package which languages exist; each language is a *pack*
(a data-only module, contract in ``base.py``). Adding a language is dropping an
``xx.py`` in here, with its word lists beside it in ``moods_xx.py`` and
``numbers_xx.py`` —
plus its message catalog in ``engine/catalogs/`` and a test suite modeled on
``tests/test_english.py``. Nothing else changes; German (2026-08-28) is the
proof, and it needed no edit to the router at all.

Discovery is deliberate about failure: a pack missing part of the contract
breaks the import loudly at startup, not a routing step quietly at runtime.
"""

from __future__ import annotations

import importlib
import pkgutil

REQUIRED = ("CODE", "PATTERNS", "NUM_WORDS", "ORDINAL_WORDS",
            "MINUTE_WORDS", "DURATIONS", "MOOD_WORDS")

#: ``{"it": <module lang.it>, "en": <module lang.en>, ...}``
PACKS = {}

for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if not hasattr(_mod, "CODE"):
        continue  # base.py and friends: helpers, not packs
    _missing = [attr for attr in REQUIRED if not hasattr(_mod, attr)]
    if _missing:
        raise ImportError(
            f"language pack {__name__}.{_info.name} is missing {_missing}")
    PACKS[_mod.CODE] = _mod
