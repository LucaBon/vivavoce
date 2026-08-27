"""Persistent, voice-editable kid-safe blocklist.

The parent can add/remove blocked songs or singers by voice; the terms must
survive restarts, so they live in a small persistent store shared by the whole
household. The concrete backend is injectable (the web app plugs in a local
JSON-file store); this module defines the contract and the no-op fallback.

Failure policy:
* **Reads fail open** — any error returns an empty list, so a storage hiccup
  degrades to the config baseline and never blocks music playback.
* **Writes fail loud** — they raise :class:`BlocklistStoreError` so the voice
  command can tell the user the change wasn't saved.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import List

# The file holds the kid-safe PIN hash and the wrong-PIN lockout alongside the
# terms, so it is written from two places (here and pro/kidsafe.py) and read
# by every request. One process-wide lock keeps those writes from interleaving.
#
# Reentrant, because it is also the default lock a store holds across its whole
# read-modify-write (see JsonBlocklistStore) and _write_json_durably then takes
# it again on the way out.
_write_lock = threading.RLock()


class BlocklistStoreError(Exception):
    """Raised when the blocklist store cannot be written."""


def _write_json_durably(path: str, state: dict) -> None:
    """Replace ``path`` with ``state`` as JSON — atomically and durably.

    A unique temp file rather than a fixed ``.tmp`` name (two writers would
    otherwise each open, truncate and rename the same one, promoting a
    half-written file or losing the race), fsync before the rename so a power
    cut leaves the old file or the new one, and 0600 because this file holds
    the kid-safe PIN hash.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    with _write_lock:
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


class JsonBlocklistStore:
    """Terms persisted in a local JSON file, under the ``terms`` key.

    The file may carry other state alongside (the web kid-safe feature keeps
    its PIN and enabled flag there): reads and writes touch only ``terms``,
    preserving everything else. Writes are atomic (tmp + ``os.replace``).

    ``lock`` is the lock held across the read-modify-write in :meth:`put`.
    Atomic writing is not enough when two objects share one file: the *other*
    writer of kidsafe.json is ``KidSafe._save``, which reads the whole state,
    changes the PIN or the lockout counter in it and writes it back. Each
    holding its own lock, they serialise against nobody, and whichever reads
    first writes last — dropping the other's change entirely. Pass the lock
    that guards the file (``appdata.lock_for(path)``) and they take turns.
    """

    def __init__(self, path: str, lock=None) -> None:
        if not path:
            raise ValueError("path is required")
        self.path = path
        # Public, because a get()/put() PAIR is a read-modify-write too and
        # only its caller knows where it begins: see guard.editing().
        self.lock = lock if lock is not None else _write_lock

    def _read_state(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self) -> List[str]:
        """Return the stored terms, or ``[]`` on any error (fail open)."""
        terms = self._read_state().get("terms") or []
        return [str(t).strip() for t in terms if str(t).strip()]

    def put(self, terms: List[str]) -> None:
        """Overwrite the stored terms. Raises on failure so callers can report it.

        Read, change and write under one lock: everything this file holds that
        is *not* ``terms`` survives only by being read here and written back,
        so an interleaving writer's change lives exactly as long as it takes
        the next reader to overwrite it.
        """
        clean = [str(t).strip() for t in (terms or []) if str(t).strip()]
        with self.lock:
            state = self._read_state()
            state["terms"] = clean
            try:
                _write_json_durably(self.path, state)
            except OSError as exc:
                raise BlocklistStoreError(
                    f"blocklist write failed: {exc}") from exc


class NoOpBlocklistStore:
    """Used when no persistence is configured: reads empty, refuses writes.

    Keeps the feature static-only (config baseline still works) instead of
    crashing when persistence isn't set up.
    """

    def get(self) -> List[str]:
        return []

    def put(self, terms: List[str]) -> None:
        raise BlocklistStoreError("blocklist persistence is not configured")
