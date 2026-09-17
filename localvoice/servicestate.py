"""Where the app keeps what it learned about its streaming services.

``engine/player/silence.py`` decides WHAT is worth remembering — which service
took a track and played none of it — and holds it in memory. This is the half
that knows about disks, which the engine deliberately does not: one small JSON
file in the data directory, next to the licence and the kid-safe blocklist.

It is state, not configuration. Nobody is meant to edit it, nothing breaks if
it is deleted (the app simply learns the same thing again, at the cost of one
silent play), and a corrupt file reads as "nothing known" rather than taking
the server down — the same fail-open rule the rest of ``appdata`` follows.
"""

from __future__ import annotations

import os
from typing import Dict

import appdata

FILE = "services.json"


class SilenceFile:
    """``read()`` / ``write()`` over ``<data dir>/services.json``.

    The shape is ``{"tidal": 1789404000.0}``: a service name, and the wall
    clock time after which it is worth trying again. Wall clock because the
    whole point is to outlive the process that learned it.
    """

    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, FILE)

    def read(self) -> Dict[str, float]:
        data = appdata.read_json(self.path, default={})
        if not isinstance(data, dict):
            return {}
        return {str(k): float(v) for k, v in data.items()
                if isinstance(v, (int, float))}

    def write(self, marks: Dict[str, float]) -> None:
        """Save the marks, or say why not and carry on without.

        Fail open in this direction too: the write happens in the middle of a
        play, and a full disk or a read-only volume is not a reason for that
        play to fail. The marks stay in memory until the restart.
        """
        try:
            appdata.atomic_write_json(self.path, marks)
        except OSError as exc:
            print(f"services.json non salvato ({exc}): quello che ho imparato "
                  f"sui servizi vale fino al riavvio.")
