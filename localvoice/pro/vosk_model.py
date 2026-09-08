# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Fetching the Vosk model the free-phrase wake word needs.

A separate module from ``vosk_wake.py`` because it is a separate job: this one
knows about URLs, archives and half-finished downloads, and nothing about
listening. Keeping it out also keeps ``urllib`` and ``zipfile`` off the import
path of the module the request handler touches.

**Why at start-up and not on first use.** The Whisper model in ``pro/asr.py``
downloads lazily, inside the first ``/transcribe`` — it can, because that
request is already understood to take a while. The wake word cannot: its first
request is a 320 ms audio chunk arriving in a stream of them, and a 50 MB fetch
inside it would time the request out, leave the browser retrying, and read as a
broken engine rather than a slow one. So it happens here, once, before the
server accepts anything — where a progress line is a normal thing to see and a
failure is a message rather than a mystery.

**Nothing here may stop the server.** Every failure — no network, a 404 from a
bumped version, a read-only data directory — returns ``None`` and lets the
caller fall back to the other engine or to the browser's. An optional feature
that cannot install itself is a degraded install, not a crash.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from typing import Callable, Optional

from pro.vosk_wake import MODEL_DIRNAMES, looks_like_model, models_dir

# Upstream publishes one zip per language on its own site. The "small" line is
# the one that matters here: ~50 MB, built for exactly this job — streaming
# recognition on a low-power box — where the full models are 1.5 GB and want a
# server. Names are upstream's own; a 404 means the version was bumped, so
# check https://alphacephei.com/vosk/models.
#
# Licences differ per model and are NOT all permissive — see
# licenses/MODELS.md. Every entry here is Apache-2.0; do not add a language
# without checking, because this engine sits behind the paid tier.
BASE_URL = "https://alphacephei.com/vosk/models"
MODEL_URLS = {lang: f"{BASE_URL}/{name}.zip"
              for lang, name in MODEL_DIRNAMES.items()}

# Generous, because it is 50 MB over somebody's home line — but finite, so a
# hung server on the other end delays start-up instead of preventing it.
TIMEOUT_SECONDS = 120


def ensure_model(lang: str, data_dir: str,
                 log: Callable[[str], None] = print,
                 opener=urllib.request.urlopen) -> Optional[str]:
    """The model directory for ``lang``, downloading it once if it is missing.

    ``None`` when there is nothing to be had — an unknown language, no
    network, a refused write. ``opener`` is injectable so tests can exercise
    every one of those without touching the network (no test in this repo may).
    """
    target_name = MODEL_DIRNAMES.get(lang)
    if not target_name:
        log(f"Nessun modello Vosk previsto per «{lang}» "
            f"(ci sono: {', '.join(sorted(MODEL_DIRNAMES))}). Indicane uno "
            f"con --wakeword-vosk-model.")
        return None

    parent = models_dir(data_dir)
    target = os.path.join(parent, target_name)
    if looks_like_model(target):
        return target

    url = MODEL_URLS[lang]
    log(f"Scarico il modello Vosk per «{lang}» (~50 MB, una volta sola). "
        f"L'ascolto continuo parte quando ha finito.")
    try:
        os.makedirs(parent, exist_ok=True)
        return _fetch_into(url, parent, target, log, opener)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile,
            ValueError) as exc:
        log(f"Modello Vosk non scaricato ({exc}). La parola chiave libera "
            f"resta spenta; riprovo al prossimo avvio, oppure scarica a mano "
            f"{url} in {parent}.")
        return None


def _fetch_into(url: str, parent: str, target: str, log, opener) -> Optional[str]:
    """Download and unpack, leaving either nothing or a complete model.

    Everything happens inside a scratch directory that is thrown away on the
    way out, and the finished model is moved into place in one step. Unpacking
    straight into ``parent`` would publish the model directory the moment the
    first entry lands, and ``looks_like_model`` would accept it — so a
    Ctrl-C, a full disk or a dropped connection would leave behind something
    that passes every check and then fails inside Kaldi on the first chunk.
    """
    scratch = tempfile.mkdtemp(prefix=".vosk-", dir=parent)
    try:
        archive = os.path.join(scratch, "model.zip")
        _download(url, archive, log, opener)
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            _refuse_escaping_members(names, scratch)
            zf.extractall(scratch)
        unpacked = os.path.join(scratch, os.path.basename(target))
        if not looks_like_model(unpacked):
            raise ValueError(f"l'archivio non contiene {os.path.basename(target)}")
        os.replace(unpacked, target)      # the one step that publishes it
        return target
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _refuse_escaping_members(names, dest: str) -> None:
    """Refuse any member that would land outside ``dest``.

    Python 3.9 predates ``zipfile``'s member filtering, so the check is
    manual. The archive comes from a known project over HTTPS, but the URL is
    version-pinned in a table bumped by hand, and a path traversal costs
    nothing to rule out (the zip half of CVE-2007-4559).
    """
    root = os.path.abspath(dest)
    for name in names:
        resolved = os.path.abspath(os.path.join(dest, name))
        if resolved != root and not resolved.startswith(root + os.sep):
            raise ValueError(f"archivio sospetto: {name!r} uscirebbe da {dest}")


def _download(url: str, dest: str, log, opener) -> None:
    with opener(url, timeout=TIMEOUT_SECONDS) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        step = 0
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            # One line per 10 MB rather than a carriage-returned bar: this
            # output goes to a log or a Docker console as often as to a
            # terminal, and a progress bar in a log file is noise nobody can
            # read.
            if done >> 20 >= step + 10:
                step = done >> 20
                log(f"  {step} MiB"
                    + (f" di {total >> 20}" if total else "") + "…")
