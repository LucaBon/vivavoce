#!/usr/bin/env python3
"""Write ``docs/demo/core-files.json``: the core files the public demo loads.

The demo page downloads ``engine/`` and ``localvoice/`` one file at a time
from jsDelivr, so it needs to know which ones. The answer is not "all of
them" — the HTTP server, the TLS setup and the Pro modules are no business of
a page with no server — and it is not a list anybody should keep by hand
either. It is **what the demo actually imports**: a clean interpreter loads
``docs/demo/boot.py``, plays every phrase in ``phrases.json`` in every
language, and reports each module file that came from the core.

    uv run python tools/demo_core_files.py           # rewrite the list
    uv run python tools/demo_core_files.py --check   # exit 1 if it is stale

The list also names the **ref** the page downloads them at: ``vX.Y.Z`` from
``pyproject.toml``, the tag ``RELEASING.md`` puts on the very ``main`` commit
Pages publishes. A tag, not ``@main``: jsDelivr keeps a branch cached for
hours after it moves, and a page from the new ``main`` running engine files
from the old one fails in ways no test here can see. A tag never moves. So a
version bump makes this list stale too — rerun the tool with the bump.

``tests/test_demo.py`` runs the check, so a new module the Router starts
importing, or a bump without a rerun, fails the suite by name instead of
failing the page in a browser.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "docs", "demo")
LIST = os.path.join(DEMO, "core-files.json")

#: Runs in a fresh interpreter, so that nothing this process (or pytest)
#: already imported is counted.
_PROBE = r"""
import json, os, sys
root, demo = sys.argv[1], sys.argv[2]
sys.path.insert(0, demo)
import boot
boot.install(root)
with open(os.path.join(demo, "phrases.json"), encoding="utf-8") as f:
    langs = json.load(f)["langs"]
for lang, phrases in langs.items():
    d = boot.Demo()
    for p in phrases:
        d.turn(p["say"], lang)
core = tuple(os.path.join(root, name) + os.sep for name in boot.CORE_DIRS)
seen = set()
for module in list(sys.modules.values()):
    path = os.path.abspath(getattr(module, "__file__", None) or "")
    if path.startswith(core):
        seen.add(os.path.relpath(path, root).replace(os.sep, "/"))
print(json.dumps(sorted(seen)))
"""


def imported_by_demo(root: str = ROOT, demo: str = DEMO) -> List[str]:
    """Repo-relative paths of every core file the demo imports.

    Run from an empty directory: ``python -c`` puts the working directory on
    ``sys.path``, and in the repo root that would let a package-style import
    resolve here that has nothing to resolve against in Pyodide.
    """
    with tempfile.TemporaryDirectory() as elsewhere:
        out = subprocess.run([sys.executable, "-c", _PROBE, root, demo],
                             capture_output=True, text=True, cwd=elsewhere)
    if out.returncode:
        raise RuntimeError(f"the demo did not run:\n{out.stderr}")
    return json.loads(out.stdout)


def release_ref(root: str = ROOT) -> str:
    """``vX.Y.Z``, from the version ``pyproject.toml`` declares."""
    with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
        found = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
    if not found:
        raise SystemExit("no version in pyproject.toml")
    return "v" + found.group(1)


def expected() -> Dict[str, Any]:
    return {"ref": release_ref(), "files": imported_by_demo()}


def listed() -> Dict[str, Any]:
    with open(LIST, encoding="utf-8") as f:
        return json.load(f)


def main(argv: List[str]) -> int:
    want = expected()
    if "--check" in argv:
        stale = want != listed()
        if stale:
            print(f"{os.path.relpath(LIST, ROOT)} is stale: "
                  f"run tools/demo_core_files.py", file=sys.stderr)
        return int(stale)
    with open(LIST, "w", encoding="utf-8") as f:
        f.write(json.dumps(want, indent=1) + "\n")
    print(f"{len(want['files'])} files at {want['ref']} "
          f"-> {os.path.relpath(LIST, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
