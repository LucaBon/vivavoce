"""English phrases for spoken media. See ``spoken_it.py`` for why these live
beside the pack, and why the direction is a lookahead."""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|half\s+an?|a\s+couple\s+of|[a-z]+)"
_UNIT = r"(?P<unit>seconds?|secs?|minutes?|mins?)"
_VERB = r"(?:skip|go|jump|move|fast[\s-]?forward|rewind|wind)"
_DIR = r"(?:back(?:wards?)?|forward|ahead)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:by\s+)?{_AMOUNT}[\s-]+{_UNIT}"
         rf"(?:\s+{_DIR})?(?:\s+please)?\s*$")
_BACK = r"(?=.*\b(?:back(?:wards?)?|rewind)\b)"

PATTERNS = {
    "seek_back": c(rf"^{_BACK}{_BODY}"),
    "seek_fwd": c(rf"^(?!.*\b(?:back(?:wards?)?|rewind)\b)"
                  rf"(?=.*\b(?:forward|ahead|skip)\b){_BODY}"),
    # "audiobook" is the marker; "read me the book X" the other way to ask.
    # Never "play the book X": that is a title as often as a request.
    "audiobook": c(r"^(?:(?:(?:play|put\s+on|start|listen\s+to|read)\s+)?"
                   r"(?:the\s+|an\s+|my\s+)?audio\s*book"
                   r"|read\s+(?:me\s+)?(?:the|a)\s+book)\s+(.+)$"),
}
