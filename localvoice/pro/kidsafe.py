# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Kid-safe mode for the web app: a PIN-protected, voice-editable blocklist.

The blocklist engine (matching, Guard, add/remove actions) lives in the AGPL
core; this module owns the *web* integration: the PIN, the per-client unlock
window, and the fail-safe policy.

Fail-safe by design: enforcement never turns itself off. If the Pro license
is later revoked (refund), an **enabled** blocklist keeps filtering — a
refund must never silently disable child protection — but configuration
changes are locked until a valid key is back.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Any, Dict, Optional

import actions
import appdata
from blocklist_store import JsonBlocklistStore

STATE_FILE = "kidsafe.json"
UNLOCK_SECONDS = 15 * 60
PBKDF2_ITERATIONS = 200_000
# Un bambino che prova PIN a raffica sulla LAN: dopo MAX_ATTEMPTS sbagliati
# si aspetta prima di poter riprovare, e l'attesa raddoppia a ogni errore
# successivo fino a LOCKOUT_MAX_SECONDS.
#
# Il conteggio è **globale**, non per client: il client id arriva dal corpo
# della richiesta, quindi un contatore per-client si azzera cambiando stringa
# — cinque tentativi freschi a ogni giro, cioè nessun limite. (E ogni
# tentativo costa 200k iterazioni PBKDF2: il ciclo era anche un modo per
# tenere occupata la CPU del server.) Il client id resta solo per la finestra
# di sblocco, che è per-dispositivo per definizione.
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
LOCKOUT_MAX_SECONDS = 3600
# Un PIN a 4 cifre sono 10.000 combinazioni: con la finestra qui sopra sono
# secoli, ma il margine costa una cifra in più. I PIN già impostati restano
# validi — il minimo vale solo per quelli nuovi.
MIN_PIN_LENGTH = 6


def _hash_pin(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex()


class KidSafe:
    def __init__(self, data_dir: str, license_mgr=None,
                 now=time.time) -> None:
        self.path = os.path.join(data_dir, STATE_FILE)
        # Held across every read-modify-write of the state file: the counter
        # below is incremented from whatever the incrementing thread last read,
        # and the server runs one thread per connection.
        self._lock = appdata.lock_for(self.path)
        # The same lock, not one of its own: the store rewrites this very file
        # — terms live in it next to the PIN hash and the lockout — so the two
        # have to take turns or each drops what the other just wrote.
        self.store = JsonBlocklistStore(self.path, lock=self._lock)
        self.license = license_mgr
        self.now = now
        self._unlocked: Dict[str, float] = {}   # client_id -> unlocked_until

    # -- state ---------------------------------------------------------------

    def _state(self) -> dict:
        return appdata.read_json(self.path, {}) or {}

    def enabled(self) -> bool:
        return bool(self._state().get("enabled"))

    def has_pin(self) -> bool:
        return bool(self._state().get("pin"))

    def pro_ok(self) -> bool:
        return bool(self.license and self.license.is_pro())

    def terms(self) -> list:
        return self.store.get()

    # -- PIN -------------------------------------------------------------------

    def _save(self, **changes: Any) -> None:
        with self._lock:
            state = self._state()
            state.update(changes)
            # 0600: this file holds the PIN hash and the lockout counter.
            appdata.atomic_write_json(self.path, state, mode=0o600)

    def _set_pin(self, pin: str) -> None:
        salt = secrets.token_bytes(16)
        self._save(pin={"salt": salt.hex(), "hash": _hash_pin(pin, salt),
                        "iterations": PBKDF2_ITERATIONS})

    def _lockout(self) -> Dict[str, Any]:
        """The install-wide wrong-PIN counter ``{"count", "retry_at"}``."""
        raw = self._state().get("lockout")
        if not isinstance(raw, dict):
            return {"count": 0, "retry_at": 0.0}
        count = raw.get("count")
        retry_at = raw.get("retry_at")
        return {
            "count": count if isinstance(count, int) and count > 0 else 0,
            "retry_at": float(retry_at) if isinstance(retry_at, (int, float))
                        else 0.0,
        }

    def locked_out_for(self) -> float:
        """Seconds still to wait before a PIN may be tried again (0 = now)."""
        lock = self._lockout()
        if lock["count"] < MAX_ATTEMPTS:
            return 0.0
        return max(0.0, lock["retry_at"] - self.now())

    def _backoff_seconds(self, count: int) -> float:
        """How long to wait after ``count`` consecutive misses."""
        if count < MAX_ATTEMPTS:
            return 0.0
        return min(LOCKOUT_SECONDS * (2 ** (count - MAX_ATTEMPTS)),
                   LOCKOUT_MAX_SECONDS)

    def verify_pin(self, pin: str, client_id: str = "") -> bool:
        """Constant-time check behind an install-wide exponential backoff.

        The lockout is consulted *before* hashing, so a client hammering the
        endpoint during its window costs nothing (200k PBKDF2 iterations per
        try is a fine way to occupy a server otherwise). ``client_id`` is
        accepted and ignored: it is client-chosen, so it can never bound
        anything — see the note on MAX_ATTEMPTS.

        The whole of it happens under the state file's lock: reading the gate,
        hashing, and writing the counter back. Checking the gate and then
        incrementing from a separately-read value is a promise of five
        attempts that concurrency collects on — every request that got in
        before the first write saw count 0, and every one of them wrote 1.
        Serialising also means the wasted hashing stops at MAX_ATTEMPTS
        instead of running once per waiting thread.
        """
        with self._lock:
            if self.locked_out_for() > 0:
                return False
            stored = self._state().get("pin") or {}
            try:
                expected = stored["hash"]
                salt = bytes.fromhex(stored["salt"])
            except (KeyError, ValueError):
                return False
            ok = secrets.compare_digest(_hash_pin(pin or "", salt), expected)
            lock = self._lockout()
            if ok:
                if lock["count"]:
                    self._save(lockout={"count": 0, "retry_at": 0.0})
            else:
                count = lock["count"] + 1
                self._save(lockout={"count": count,
                                    "retry_at": self.now()
                                    + self._backoff_seconds(count)})
            return ok

    # -- unlock window ---------------------------------------------------------

    def _sweep_unlocked(self) -> None:
        """Drop expired unlock windows. Without this the map grows one entry
        per browser that ever typed the PIN, forever."""
        now = self.now()
        for client in [c for c, until in self._unlocked.items() if until <= now]:
            self._unlocked.pop(client, None)

    def is_unlocked(self, client_id: str) -> bool:
        return self.now() < self._unlocked.get(client_id, 0)

    def unlock(self, client_id: str, pin: str) -> bool:
        if not self.verify_pin(pin, client_id):
            return False
        self._sweep_unlocked()
        self._unlocked[client_id] = self.now() + UNLOCK_SECONDS
        return True

    def lock(self, client_id: str) -> None:
        self._unlocked.pop(client_id, None)

    # -- configuration (Pro-gated; enforcement below is not) -------------------

    def enable(self, pin: str, client_id: str) -> Dict[str, Any]:
        """Turn enforcement on. First run sets the PIN; later runs require it."""
        if not self.pro_ok():
            return {"ok": False, "error": "pro_required"}
        pin = (pin or "").strip()
        if not self.has_pin():
            if len(pin) < MIN_PIN_LENGTH:
                return {"ok": False, "error": "pin_too_short",
                        "min": MIN_PIN_LENGTH}
            self._set_pin(pin)
        elif not self.verify_pin(pin, client_id):
            wait = self.locked_out_for()
            if wait > 0:
                return {"ok": False, "error": "locked_out",
                        "retry_in": int(wait) + 1}
            return {"ok": False, "error": "wrong_pin"}
        self._save(enabled=True)
        self._unlocked[client_id] = self.now() + UNLOCK_SECONDS
        return {"ok": True}

    def disable(self, client_id: str) -> Dict[str, Any]:
        if not self.pro_ok():
            return {"ok": False, "error": "pro_required"}
        if not self.is_unlocked(client_id):
            return {"ok": False, "error": "locked"}
        self._save(enabled=False)
        return {"ok": True}

    def edit_terms(self, op: str, term: str, client_id: str) -> Dict[str, Any]:
        if not self.pro_ok():
            return {"ok": False, "error": "pro_required"}
        if not self.is_unlocked(client_id):
            return {"ok": False, "error": "locked"}
        result = (actions.add_block if op == "add" else actions.remove_block)(
            self.store, term, is_owner=True)
        # add_block/remove_block already say no — an empty term, or a store
        # that cannot be written (a read-only data dir) — and this used to
        # answer "ok" over the top of them, so the panel cleared the input and
        # showed nothing: a term that was never saved looked saved.
        if not result.ok:
            return {"ok": False, "error": "save_failed", "speech": str(result)}
        return {"ok": True, "speech": str(result)}

    # -- enforcement (never Pro-gated: see the fail-safe note above) -----------

    def guard_for(self, client_id: str) -> Optional[actions.Guard]:
        """The Guard for this request: restrictive only when kid-safe is
        enabled and the client isn't PIN-unlocked."""
        if not self.enabled() or self.is_unlocked(client_id):
            return None
        return actions.Guard(restricted=True, blocklist=self.terms())
