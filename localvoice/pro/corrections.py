# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Corrections the household confirmed: «when you hear X, I mean Y».

The index of known names (``name_index.py``) can only help where what was
heard *sounds like* a known name. «coming di eminem e johnny» does not sound
like «Kamin di EMIN & JONY» closely enough for anything to dare — and worse,
it is a sentence that plays something (Eminem), so nothing after the fact
should overrule it. Only the person who asked can say that it was wrong, and
how it should have been heard. This is where they said so
(docs/name-recognition-design.md, phase 2).

A correction is kept only when somebody tapped "remember" under an answer:
never learnt silently (§5.2). It is applied *before* the turn is routed, to
spoken turns only, and only on an exact match of what was heard — by its
letters or, failing that, by its sound key: a confirmed rule is precise, not
fuzzy. Persisted in ``corrections.json`` beside the play history.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import appdata
from pro.phonetic import fold, phonetic_key

#: How many corrections are kept. Past it, the one used least recently goes.
MAX_CORRECTIONS = 500

#: The longest phrase kept on either side: a sentence somebody said, not a
#: document somebody pasted.
MAX_PHRASE = 200


class Corrections:
    """The confirmed corrections, persisted. Thread-safe."""

    def __init__(self, path: str, *, clock: Callable[[], float] = time.time,
                 max_items: int = MAX_CORRECTIONS) -> None:
        self.path = path
        self._clock = clock
        self._max = max_items
        self._lock = threading.RLock()
        state = appdata.read_json(path, {}) or {}
        items = state.get("corrections") if isinstance(state, dict) else None
        self._items: List[Dict[str, Any]] = [
            c for c in (items or [])
            if isinstance(c, dict) and c.get("heard") and c.get("meant")
            and c.get("id")]

    def add(self, heard: str, meant: str, lang: str = "it") -> Optional[dict]:
        """Keep «when you hear ``heard``, I mean ``meant``». The same thing
        heard again replaces the old meaning: the latest confirmation wins.
        None when there is nothing to keep, or nothing would change."""
        heard = (heard or "").strip()[:MAX_PHRASE]
        meant = (meant or "").strip()[:MAX_PHRASE]
        if not fold(heard) or not fold(meant) or fold(heard) == fold(meant):
            return None
        lang = lang if isinstance(lang, str) and lang else "it"
        with self._lock:
            self._items = [c for c in self._items
                           if not (c.get("lang") == lang
                                   and fold(c.get("heard")) == fold(heard))]
            item = {"id": uuid.uuid4().hex[:12], "heard": heard, "meant": meant,
                    "lang": lang, "used": 0, "last": self._clock()}
            self._items.append(item)
            if len(self._items) > self._max:
                self._items.sort(key=lambda c: -float(c.get("last") or 0))
                del self._items[self._max:]
            self._save()
            return dict(item)

    def forget(self, item_id: str) -> bool:
        with self._lock:
            kept = [c for c in self._items if c.get("id") != item_id]
            if len(kept) == len(self._items):
                return False
            self._items = kept
            self._save()
            return True

    def items(self) -> List[dict]:
        """Newest first — for the settings page."""
        with self._lock:
            return sorted((dict(c) for c in self._items),
                          key=lambda c: -float(c.get("last") or 0))

    def lookup(self, heard: str, lang: str = "it") -> Optional[dict]:
        """The correction for exactly this phrase, or None. Letters first;
        the sound key only when no correction matches by letters, and only
        an identical key — «coming» and «komming» are the same rule, «coming»
        and «come in» are not."""
        f, key = fold(heard), phonetic_key(heard, lang)
        if not f:
            return None
        with self._lock:
            mine = [c for c in self._items if c.get("lang", "it") == lang]
            hit = next((c for c in mine if fold(c["heard"]) == f), None)
            if hit is None and key:
                hit = next((c for c in mine
                            if phonetic_key(c["heard"], lang) == key), None)
            if hit is None:
                return None
            hit["used"] = int(hit.get("used") or 0) + 1
            hit["last"] = self._clock()
            self._save()
            return dict(hit)

    def _save(self) -> None:
        try:
            appdata.atomic_write_json(self.path, {"corrections": self._items})
        except OSError:
            pass
