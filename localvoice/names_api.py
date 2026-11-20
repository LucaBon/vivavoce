"""``/names``: the settings section for misheard names, and the "remember"
tap under an answer (docs/name-recognition-design.md, phase 2).

The core only routes: every decision — the licence, what a change does, what
is shown — belongs to the injected ``names`` feature (``pro/names.py``),
whose ``state()`` and ``act(payload)`` this calls. Without it (a build with
no ``pro/``), the section reads as not available, and every change is
refused with the same shape.
"""

from __future__ import annotations

import json


def names_routes(names=None):
    """The ``/names`` routes, bound to the feature object behind them."""

    class NamesRoutes:
        def _names_status(self):
            if names is None:
                self._send(200, json.dumps({"pro": False, "available": False}))
                return
            self._send(200, json.dumps(dict(names.state(), available=True),
                                       ensure_ascii=False))

        def _names_action(self):
            if names is None:
                self._send(200, json.dumps(
                    {"ok": False, "error": "unavailable", "available": False}))
                return
            result = names.act(self._read_json_object())
            self._send(200, json.dumps(dict(result, available=True),
                                       ensure_ascii=False))

    return NamesRoutes
