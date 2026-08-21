"""``python -m localvoice`` — same entry point as ``python localvoice/server.py``."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(server.main())
