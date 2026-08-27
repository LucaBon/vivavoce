"""Per-install configuration and data directory, stdlib only.

Two jobs, shared by the license cache and the kid-safe store:

* ``env()`` — one place that knows the app's env-var namespace, so a future
  rename only touches the prefixes below (the old prefix keeps working for a
  release, with a deprecation note).
* ``data_dir()`` + atomic JSON read/write — one persistent directory per
  deploy target: Docker/HA pass ``--data-dir`` (a mounted volume), Windows
  gets ``%APPDATA%``, Linux/macOS the XDG data dir. Writes are atomic
  (tmp + ``os.replace``) so a crash mid-write never corrupts state.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from typing import Any, Dict, Optional

# Il namespace delle variabili d'ambiente. LEGACY_PREFIX (il nome pre-rebrand)
# viene letto come ripiego per un rilascio, poi sparisce: chi ha ancora i
# vecchi nomi configurati continua a funzionare ma vede l'avviso.
PRIMARY_PREFIX = "VIVAVOCE"
LEGACY_PREFIX: Optional[str] = "SQUEEZESAY"

# Il nome della cartella dati per-utente (Windows %APPDATA%\<qui>, XDG in
# minuscolo su Linux/macOS).
APP_DIR_NAME = "Vivavoce"

_warned_legacy = set()


def env(name: str, default: Optional[str] = None,
        environ=os.environ) -> Optional[str]:
    """Read ``<PRIMARY_PREFIX>_<name>``, falling back to the legacy prefix.

    The fallback prints a one-time deprecation note per variable, so existing
    setups keep working across the rename but users learn the new name.
    """
    value = environ.get(f"{PRIMARY_PREFIX}_{name}")
    if value is not None:
        return value
    if LEGACY_PREFIX:
        value = environ.get(f"{LEGACY_PREFIX}_{name}")
        if value is not None:
            if name not in _warned_legacy:
                _warned_legacy.add(name)
                print(f"Nota: {LEGACY_PREFIX}_{name} è deprecata, "
                      f"usa {PRIMARY_PREFIX}_{name}.")
            return value
    return default


def data_dir(cli_value: Optional[str] = None, environ=os.environ) -> str:
    """The directory for persistent server-side state, created on first use.

    Resolution order: explicit ``--data-dir`` → ``<PREFIX>_DATA_DIR`` env
    (Docker and the HA add-on already export it, pointing at their volume) →
    ``%APPDATA%`` on Windows → XDG data dir elsewhere.
    """
    path = cli_value or env("DATA_DIR", environ=environ)
    if not path:
        if os.name == "nt":
            base = environ.get("APPDATA") or os.path.expanduser("~")
            path = os.path.join(base, APP_DIR_NAME)
        else:
            base = environ.get("XDG_DATA_HOME") or os.path.expanduser(
                os.path.join("~", ".local", "share"))
            path = os.path.join(base, APP_DIR_NAME.lower())
    os.makedirs(path, exist_ok=True)
    return path


def app_version(environ=os.environ) -> str:
    """The app version, for display and for the "report a phrase" template.

    The truth lives in ``pyproject.toml`` (shipped next to ``engine/`` and
    ``localvoice/`` by every deploy target, so there is no third hand-bumped
    copy); ``<PREFIX>_VERSION`` overrides it, and a missing file degrades to
    ``"unknown"`` rather than an exception — the version is nice-to-have,
    never load-bearing.
    """
    override = env("VERSION", environ=environ)
    if override:
        return override
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
            match = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
    except OSError:
        return "unknown"
    return match.group(1) if match else "unknown"


def read_json(path: str, default: Any = None) -> Any:
    """Parsed JSON content of ``path``, or ``default`` on any error.

    Fail-open on purpose: a missing or corrupt state file degrades to the
    defaults instead of taking the server down.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# One lock for every state file this process writes. The files are small and
# written rarely (a PIN change, an activation, a blocklist edit), so a single
# lock costs nothing and removes the interleaving two threads could otherwise
# produce — the HTTP server is thread-per-request, and /kidsafe is reachable
# from every phone in the house at once.
# One reentrant lock per file, so a read-modify-write of a JSON state file can
# be made atomic against other threads touching the same file. _write_lock
# below guards the write alone, which is enough to keep a file from being
# corrupted and not nearly enough to keep two threads from each reading the
# same counter and each writing back "one more than what I read".
_path_locks_guard = threading.Lock()
_path_locks: Dict[str, "threading.RLock"] = {}


def lock_for(path: str) -> "threading.RLock":
    """The lock guarding read-modify-write cycles on ``path``.

    Keyed on the absolute path, so two objects pointing at one file — and
    kid-safe has exactly that, a KidSafe and a JsonBlocklistStore on the same
    kidsafe.json — serialise against each other rather than each holding a
    private lock and neither noticing the other.
    """
    key = os.path.abspath(path)
    with _path_locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_locks[key] = lock
        return lock


_write_lock = threading.Lock()


def atomic_write_json(path: str, obj: Any, *, mode: Optional[int] = None) -> None:
    """Write ``obj`` as JSON, atomically and durably.

    A unique same-directory temp file (not a fixed ``.tmp`` name, which two
    concurrent writers would each open, truncate and rename — promoting a
    half-written file or losing the race with ``FileNotFoundError``), flushed
    and ``fsync``-ed before the rename so a power cut leaves either the old
    file or the new one, never an empty one. That last case mattered: an
    empty ``trial.json`` reads as "no window yet" and silently re-opens a
    fresh 14 days.

    ``mode`` sets the permissions of the finished file (``0o600`` for the
    files that hold secrets); the default follows the process umask.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    with _write_lock:
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".",
                                   suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode if mode is not None else 0o644)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        # The rename itself is only durable once the directory entry is: an
        # fsync on the directory. Not available on Windows, where the rename
        # is already atomic and there is nothing further to force.
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)
