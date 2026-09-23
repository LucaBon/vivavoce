"""What the demo page calls: the real Router, handed the pretend hi-fi.

``demo.js`` does three things and then only ever calls into here: it loads
Pyodide, writes the files in ``core-files.json`` under one root, and calls
:func:`install` with that root. Every turn after that is :meth:`Demo.turn`,
whose answer is JSON — the JavaScript side renders it and decides nothing.
Keeping the page's logic here, in Python, is what lets ``tests/test_demo.py``
hold it to account without a browser.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

#: ``engine/`` and ``localvoice/`` import each other by flat name
#: (``import actions``), exactly as ``localvoice/server.py`` and
#: ``tests/conftest.py`` arrange it.
CORE_DIRS = ("engine", "localvoice")


def install(root: str) -> None:
    """Put the core written under ``root`` where its imports expect it."""
    for name in CORE_DIRS:
        path = os.path.join(root, name)
        if path not in sys.path:
            sys.path.insert(0, path)


def catalogue() -> list:
    """Everything the pretend hi-fi has, for the page to show: a visitor who
    cannot see the shelf cannot tell «not found» from «not understood»."""
    from hifi import CATALOGUE

    return [{"title": t, "artist": a, "album": al} for t, a, al, _ in CATALOGUE]


def catalogue_json() -> str:
    return json.dumps(catalogue(), ensure_ascii=False)


class Demo:
    """One conversation with one pretend hi-fi."""

    def __init__(self, hifi: Optional[Any] = None):
        from hifi import DemoHifi
        from router import Router

        self.hifi = hifi if hifi is not None else DemoHifi()
        # No default service and no source: this hi-fi has no streaming
        # services, and a reply that ended «da TIDAL» would be naming one.
        self.router = Router(self.hifi, default_service=None, services=())

    def turn(self, text: str, lang: str = "it") -> Dict[str, Any]:
        """One phrase in, what the product answered and did out.

        ``told`` is every command the hi-fi received during this turn — the
        half of the answer a real hi-fi would make audible, and the proof that
        a refusal really did start nothing.
        """
        before = len(self.hifi.calls)
        out = self.router.handle_many([text], None, lang)
        told = [{"name": name, "args": [str(a) for a in args]}
                for name, args in self.hifi.calls[before:]]
        return {"speech": str(out["speech"]), "ok": bool(out["ok"]),
                "needs_choice": bool(out.get("needs_choice")),
                "choices": list(out.get("choices") or []),
                "told": told, "now_playing": self.hifi.status_info()}

    def turn_json(self, text: str, lang: str = "it") -> str:
        """:meth:`turn` for the page: one string crosses into JavaScript,
        rather than a Python dict proxy the page would have to free."""
        return json.dumps(self.turn(text, lang), ensure_ascii=False)
