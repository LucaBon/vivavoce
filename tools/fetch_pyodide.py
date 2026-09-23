#!/usr/bin/env python3
"""Download the Pyodide runtime the public demo loads, for the browser tests.

The demo page (``docs/demo/``) loads Pyodide from jsDelivr. The test that
drives that page (``tests/e2e/test_demo_page.py``) may not touch the network,
so it serves the same files from here instead, routed in by Playwright. This
is development setup, like ``playwright install chromium``: run it once.

    uv run python tools/fetch_pyodide.py

The version is read from ``docs/demo/demo.js`` — the one place it is written —
so the page and the test cannot drift apart. Files land in
``.cache/pyodide/<version>/`` (git-ignored); ones already there are kept.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_JS = os.path.join(ROOT, "docs", "demo", "demo.js")

#: What ``loadPyodide()`` fetches for the bare interpreter: the demo loads no
#: packages, so nothing else in the distribution is ever asked for.
FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
         "python_stdlib.zip", "pyodide-lock.json")


def version() -> str:
    with open(DEMO_JS, encoding="utf-8") as f:
        found = re.search(r'PYODIDE_VERSION\s*=\s*"([^"]+)"', f.read())
    if not found:
        raise SystemExit(f"no PYODIDE_VERSION in {DEMO_JS}")
    return found.group(1)


def cache_dir(ver: str = "") -> str:
    return os.path.join(ROOT, ".cache", "pyodide", ver or version())


def main() -> int:
    ver = version()
    dest = cache_dir(ver)
    os.makedirs(dest, exist_ok=True)
    base = f"https://cdn.jsdelivr.net/pyodide/v{ver}/full/"
    for name in FILES:
        path = os.path.join(dest, name)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        with urllib.request.urlopen(base + name, timeout=120) as r:
            body = r.read()
        with open(path + ".part", "wb") as f:
            f.write(body)
        os.replace(path + ".part", path)
        print(f"{name}: {len(body) // 1024} KiB")
    print(f"Pyodide {ver} -> {os.path.relpath(dest, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
