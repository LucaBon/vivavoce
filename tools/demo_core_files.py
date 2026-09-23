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

``tests/test_demo.py`` runs the check, so a new module the Router starts
importing fails the suite by name instead of failing the page in a browser.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List

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
    """Repo-relative paths of every core file the demo imports."""
    out = subprocess.run([sys.executable, "-c", _PROBE, root, demo],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def listed() -> List[str]:
    with open(LIST, encoding="utf-8") as f:
        return json.load(f)


def main(argv: List[str]) -> int:
    files = imported_by_demo()
    if "--check" in argv:
        stale = files != listed()
        if stale:
            print(f"{os.path.relpath(LIST, ROOT)} is stale: "
                  f"run tools/demo_core_files.py", file=sys.stderr)
        return int(stale)
    with open(LIST, "w", encoding="utf-8") as f:
        f.write(json.dumps(files, indent=1) + "\n")
    print(f"{len(files)} files -> {os.path.relpath(LIST, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
