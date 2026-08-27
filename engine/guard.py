"""What must not be played, and who may change that.

The kid-safe blocklist: parsing it, matching it, the per-request
:class:`Guard` the router hands to every action, and the owner-only voice
commands that edit the stored terms. Kept together because a blocklist is only
as good as the agreement between what goes *in* it and what is checked
*against* it, and that agreement is easiest to keep when both are on one screen.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from blocklist_store import BlocklistStoreError
from matching import (BLOCKLIST, GATE, ActionResult, _normalize,
                      _normalize_apart)
from messages import msg

# Spoken when a restricted (non-owner) speaker asks for a blocked song/singer.
BLOCKED_SPEECH = msg("blocked")
# Spoken when a non-owner tries to change the blocklist by voice.
NOT_OWNER_SPEECH = msg("not_owner")


def parse_blocklist(raw) -> List[str]:
    """Turn a comma/newline string (or list) into de-duplicated display terms.

    Terms are kept in their original spoken/typed form (so they read back nicely
    in ``list_blocks``); matching normalizes on the fly in :func:`is_blocked`."""
    if not raw:
        return []
    parts = raw if isinstance(raw, (list, tuple)) else re.split(r"[,\n]", str(raw))
    out: List[str] = []
    seen = set()
    for part in parts:
        term = str(part).strip()
        norm = _normalize(term)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(term)
    return out


def is_blocked(text: Optional[str], blocklist: Optional[List[str]]) -> bool:
    """True if any blocklist term appears in ``text`` as a whole word (normalized).

    Word-boundary matching avoids false positives like a blocked 'ass' hitting
    'bass', while still catching multi-word terms and inflections around them."""
    # Two normalizations, because one boundary rule cannot serve both spellings:
    # _normalize deletes the apostrophe, so it catches the recogniser's «dont
    # stop me now»; _normalize_apart keeps it as a separator, so a blocked term
    # still stands alone in "L'Estasi dell'Oro" and "Eminem's Greatest Hits".
    # A term is blocked if it stands as a whole word in EITHER reading.
    haystacks = [(_normalize(text), _normalize),
                 (_normalize_apart(text), _normalize_apart)]
    haystacks = [(hay, norm_fn) for hay, norm_fn in haystacks if hay]
    if not haystacks:
        return False
    for term in blocklist or []:
        for hay, norm_fn in haystacks:
            term_norm = norm_fn(term)
            if term_norm and re.search(rf"\b{re.escape(term_norm)}\b", hay):
                return True
    return False


# Every field of a resolved item that names something a blocklist term could
# be about. Checking only ``title`` was the hole: with ["Eminem"] blocked, a
# child asking «metti Lose Yourself» never says the blocked word, so the
# request text passed — and the track played, artist read aloud.
ITEM_NAME_FIELDS = ("title", "artist", "album", "name")


def is_blocked_item(item: Optional[Dict], blocklist: Optional[List[str]]) -> bool:
    """True if any blocklist term matches ANY name field of a resolved item."""
    if not item:
        return False
    return any(is_blocked(item.get(f), blocklist) for f in ITEM_NAME_FIELDS)


class Guard:
    """Speaker-based access gate. When ``restricted`` is True, any request text
    matching ``blocklist`` is refused with :data:`BLOCKED_SPEECH`. When it's
    False the guard is transparent, so passing ``guard=None`` is also a no-op."""

    def __init__(self, restricted: bool = False, blocklist: Optional[List[str]] = None):
        self.restricted = restricted
        self.blocklist = blocklist or []

    def blocks(self, *texts: Optional[str]) -> bool:
        if not self.restricted:
            return False
        return any(is_blocked(t, self.blocklist) for t in texts if t)

    def blocks_item(self, item: Optional[Dict]) -> bool:
        """The single choke point for a *resolved* item (a track, album,
        artist or favourite dict): checks every name field, not just the
        title. Use this everywhere something is about to be played, queued or
        read aloud — the request text alone never sees the artist."""
        if not self.restricted:
            return False
        return is_blocked_item(item, self.blocklist)


# -- voice-editable blocklist (owner only) --------------------------------
# These edit only the *dynamic* stored terms; the config KIDSAFE_BLOCKLIST
# baseline is permanent and can't be removed by voice.
# "Already blocked" and "not in the list" are ``ok=True`` on purpose, and it is
# not a judgement call about wording. ``ok`` is what ``handle_many`` reads to
# decide whether to try the NEXT speech-recognition alternative, and a second
# alternative of an edit command is a *different term*: calling "it is already
# blocked" a miss would go on to block whatever the second-best transcription
# heard. The request is satisfied either way — the term is in the list, or it
# is not — so the honest answer is also the safe one.
def add_block(store, term: Optional[str], *, is_owner: bool) -> ActionResult:
    """Add a song/singer term to the blocklist. Owner-gated."""
    if not is_owner:
        return ActionResult(msg("not_owner"), ok=False, kind=GATE)
    term = (term or "").strip()
    if not term:
        return ActionResult(msg("ask_block"), ok=False, kind=BLOCKLIST)
    try:
        terms = store.get()
        if any(_normalize(t) == _normalize(term) for t in terms):
            return ActionResult(msg("already_blocked", term=term), ok=True, kind=BLOCKLIST)
        store.put(terms + [term])
    except BlocklistStoreError:
        return ActionResult(msg("blocklist_save_error"), ok=False, kind=BLOCKLIST)
    return ActionResult(msg("block_added", term=term), ok=True, kind=BLOCKLIST)


def remove_block(store, term: Optional[str], *, is_owner: bool) -> ActionResult:
    """Remove a term from the blocklist. Owner-gated."""
    if not is_owner:
        return ActionResult(msg("not_owner"), ok=False, kind=GATE)
    term = (term or "").strip()
    if not term:
        return ActionResult(msg("ask_unblock"), ok=False, kind=BLOCKLIST)
    try:
        terms = store.get()
        kept = [t for t in terms if _normalize(t) != _normalize(term)]
        if len(kept) == len(terms):
            return ActionResult(msg("not_in_blocklist", term=term), ok=True, kind=BLOCKLIST)
        store.put(kept)
    except BlocklistStoreError:
        return ActionResult(msg("blocklist_update_error"), ok=False, kind=BLOCKLIST)
    return ActionResult(msg("block_removed", term=term), ok=True, kind=BLOCKLIST)


def list_blocks(store, *, is_owner: bool) -> ActionResult:
    """Read the blocked terms aloud. Owner-gated."""
    if not is_owner:
        return ActionResult(msg("not_owner"), ok=False, kind=GATE)
    terms = store.get()
    if not terms:
        return ActionResult(msg("blocklist_empty"), ok=True, kind=BLOCKLIST)
    return ActionResult(msg("blocklist_listing", terms=", ".join(terms)),
                        ok=True, kind=BLOCKLIST)
