"""Persistent memory of disambiguation choices ("brick" -> the user's Pt. 2).

When a 'did you mean' ask is answered, the (query -> chosen title) pair is
remembered here; the next time the same ambiguous query comes in, the router
plays the remembered choice straight away instead of asking again. This is
personalization the transparent way: one local JSON file the user can read,
edit, or delete.

Failure policy mirrors :mod:`blocklist_store`: reads fail open (no memory is
just the old ask-again behaviour), writes fail silent — losing one remembered
pick must never break the pick itself.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Optional

# The file is bounded: the oldest remembered choices roll off. A household
# does not produce thousands of genuinely ambiguous queries.
MAX_CHOICES = 200


def _normalize(text) -> str:
    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


class PrefsStore:
    """Remembered disambiguation picks in a local JSON file, under the
    ``choices`` key ({normalized query: chosen title}). Writes are atomic
    (tmp + ``os.replace``) and preserve any other state in the file."""

    def __init__(self, path: str) -> None:
        if not path:
            raise ValueError("path is required")
        self.path = path

    def _read_state(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, query) -> Optional[str]:
        """The remembered title for ``query``, or ``None`` (fail open)."""
        key = _normalize(query)
        if not key:
            return None
        choices = self._read_state().get("choices") or {}
        value = choices.get(key) if isinstance(choices, dict) else None
        return str(value) if value else None

    def put(self, query, title) -> None:
        """Remember ``title`` as the answer for ``query``. Best-effort: any
        storage error is swallowed — the pick already played."""
        key, value = _normalize(query), str(title or "").strip()
        if not key or not value:
            return
        state = self._read_state()
        choices = state.get("choices")
        if not isinstance(choices, dict):
            choices = {}
        choices.pop(key, None)  # re-insert last so insertion order = recency
        choices[key] = value
        while len(choices) > MAX_CHOICES:
            choices.pop(next(iter(choices)))
        state["choices"] = choices
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass
