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
from typing import Any, Dict, List, Optional

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


def started(told: List[Dict[str, Any]]) -> bool:
    """Did this turn start something new — not a pause, a seek, a volume?"""
    return any(c["name"].startswith("play_") for c in told)


def queued(told: List[Dict[str, Any]]) -> bool:
    """Did this turn put something in the queue rather than play it?"""
    return any(c["name"].startswith(("add_", "insert_")) for c in told)


def verdict(text: str, lang: str, naive: Any, told: List[Dict[str, Any]],
            now: Dict[str, Any]) -> str:
    """What the page says about the typical assistant's column:

    * ``n/a`` — nothing to compare: not a request to play, or one to queue
      («metti Money in coda» is not «metti Money», and its first hit would
      be marked wrong for being the very record that was queued);
    * ``same`` — the same record, or nothing on both sides;
    * ``lucky`` — Vivavoce started nothing, and the first hit looks like
      what was asked for (:func:`naive.resembles`): said, not scored;
    * ``differs`` — it would have started a record Vivavoce did not.
    """
    from naive import NOT_A_PLAY, resembles

    if naive == NOT_A_PLAY or queued(told):
        return NOT_A_PLAY
    if not started(told):
        if naive is None:
            return "same"
        return "lucky" if resembles(text, lang, naive) else "differs"
    if naive is None:
        return "differs"
    same = (naive["title"], naive["artist"]) == (now.get("title"), now.get("artist"))
    return "same" if same else "differs"


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
        a refusal really did start nothing. ``naive`` and ``verdict`` are the
        other column of the page: what a keyword search would have started
        (``naive.py``), and whether that is what Vivavoce did.
        """
        from naive import naive_turn

        before = len(self.hifi.calls)
        out = self.router.handle_many([text], None, lang)
        told = [{"name": name, "args": [str(a) for a in args]}
                for name, args in self.hifi.calls[before:]]
        now = self.status()
        naive = naive_turn(text, lang)
        return {"speech": str(out["speech"]), "ok": bool(out["ok"]),
                "needs_choice": bool(out.get("needs_choice")),
                "choices": list(out.get("choices") or []),
                "told": told, "now_playing": now,
                "naive": naive, "verdict": verdict(text, lang, naive, told, now)}

    def status(self) -> Dict[str, Any]:
        """What the hi-fi is doing, and what it will play after it."""
        now = dict(self.hifi.status_info())
        now["upcoming"] = self.hifi.queue_upcoming(5) if now.get("title") else []
        return now

    def status_json(self) -> str:
        """What the hi-fi is doing now, between phrases: a record ends and
        the next one starts without anybody asking."""
        return json.dumps(self.status(), ensure_ascii=False)

    def turn_json(self, text: str, lang: str = "it") -> str:
        """:meth:`turn` for the page: one string crosses into JavaScript,
        rather than a Python dict proxy the page would have to free."""
        return json.dumps(self.turn(text, lang), ensure_ascii=False)
