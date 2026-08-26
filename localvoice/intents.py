"""The intent table: one spoken phrase in, one action out.

Split out on its own because the size ratchet in ``tests/test_packaging.py``
said exactly this («the intent table has outgrown its module»). It is the part
that grows every time the product learns something new to understand, so it now
grows alone instead of dragging the dispatch flow, the conversation state and
the number parsing over the line with it.

The numbered steps are an order, not a list: earlier ones win, that ordering is
load-bearing in several places, and each of those places says so where it sits.

A mixin over :class:`router.Router`, for the reason given in
``conversation.py``: the routing reads and writes the router\'s own state.
"""

from __future__ import annotations

import re

import actions
import moods
from conversation import MOOD_TTL
from messages import msg
from parsing import _as_number, _parse_minutes, _service_re, _source_suffix


class IntentTable:
    """Every phrase the router knows how to act on."""

    def _route(self, t: str, source: str, P: dict) -> str:
        # 0) kid-safe voice management (Pro; list/edit gated on the PIN unlock).
        if self.kidsafe:
            m = (P["block_add"].match(t) or P["block_remove"].match(t)
                 or P["block_list"].match(t))
            if m:
                if not self.kidsafe.pro_ok():
                    return actions.ActionResult(msg("pro_required"), ok=False,
                                                kind=actions.GATE)
                is_owner = self.kidsafe.is_unlocked(self.client_id)
                if P["block_add"].match(t):
                    return actions.add_block(
                        self.kidsafe.store,
                        P["block_add"].match(t).group(1).strip(),
                        is_owner=is_owner)
                if P["block_remove"].match(t):
                    return actions.remove_block(
                        self.kidsafe.store,
                        P["block_remove"].match(t).group(1).strip(),
                        is_owner=is_owner)
                return actions.list_blocks(self.kidsafe.store, is_owner=is_owner)

        # 0b) queue management (song-level: "aggiungi X alla coda" / "add X to
        # the queue", "metti X dopo questa" / "play X next", clear/list) and
        # favorites/radio. Checked here, ahead of `is_play` and the transport
        # block below, on purpose: "aggiungi"/"add ... to the queue" aren't
        # play verbs, so `is_play` would stay False for them and let a title
        # containing a bare transport word ("aggiungi Stop alla coda") get
        # mistaken for actions.pause() before ever reaching these patterns —
        # each one here is anchored on its own distinctive marker phrase
        # ("alla coda"/"to the queue", "dopo questa"/"next", ...), so moving
        # them first can't itself swallow a genuine transport command. The UI
        # source selector decides where a queued song comes from, exactly
        # like a plain play request (step 8) — explicit "da tidal .../from my
        # music ..." overrides aren't supported for queue commands (out of
        # scope; those phrases still work for a plain play request).
        if P["queue_clear"].search(t):
            return actions.clear_queue(self.lms)
        if P["queue_list"].search(t):
            return actions.queue_list(self.lms, guard=self._guard)
        m = P["queue_add"].search(t)
        if m:
            return self._resolve_queue(m.group(1).strip(), "add", source)
        m = P["queue_insert"].search(t)
        if m:
            return self._resolve_queue(m.group(1).strip(), "insert", source)
        # Favorites & radio — LMS core feature, source-independent (not a
        # streaming service, so the source selector doesn't apply).
        if P["favorites"].search(t):
            return actions.play_favorites(self.lms, guard=self._guard)
        m = P["radio"].search(t)
        if m:
            return actions.play_radio(self.lms, m.group(1).strip(), guard=self._guard)

        # 0c) vague requests — «metti qualcosa di rilassante», «music for
        # dinner» (engine/moods.py). Sitting above the play verbs, and above
        # the transport block below, is only safe because three things have to
        # hold at once, and the third was the one this step originally missed:
        # the phrase has to START as a request to play (the pattern is anchored
        # — see lang/it.py, where the list of phrases that used to start the
        # music while asking to stop it is written out), a marker noun a title
        # never carries has to follow immediately, and what that captures has
        # to BE a whole mood word. «metti la musica di Vasco Rossi» clears the
        # first two and fails the third, and goes on to the artist path
        # exactly as before.
        #
        # Two things are deliberately out of scope, both of them the same
        # limitation the queue block above already carries. A mood into the
        # queue («aggiungi qualcosa di rilassante alla coda»): queue_add is
        # checked first, so that phrase keeps behaving as it did. And an
        # explicit source override («dalla mia musica metti qualcosa di
        # rilassante» / "from my music, play something relaxing"): those do not
        # start as a play request, so the anchor above turns them down and they
        # fall through to the local-prefix path unchanged. The UI source
        # selector is what decides where a mood comes from — exactly like a
        # queued song. Worth knowing that this makes the most natural way to
        # ask for a local mood out loud not work; the selector is the answer
        # today, and lifting it means letting the prefix run first.
        if self.mood is not None and P["mood_another"].search(t):
            self._mood_turn = True
            return self._play_mood(source)
        m = P["mood"].search(t)
        if m:
            tail = m.group(1).strip()
            key = moods.match_mood(tail, self._mood_words)
            if key:
                self.mood = {"key": key, "used": []}
                self.mood_until = self.now() + MOOD_TTL
                self._mood_turn = True
                res = self._play_mood(source)
                # A mood with nothing to offer is not an answer: fall through
                # and let the rest of the routing have the phrase. "play some
                # Fun" names a band, and an empty mood must not be why it
                # stops being looked for.
                if getattr(res, "kind", None) != "mood_empty":
                    return res
                self._mood_turn = False

        # A play command carries a title after the verb; its transport-sounding
        # words ("Don't Stop Me Now" -> "stop") must NOT be mistaken for
        # transport controls, or the song is never played. "in pausa"/"on pause"
        # stays an explicit pause even with a play verb ("metti in pausa").
        is_play = bool(P["is_play"].search(t))

        # 1) transport & info (source-independent). The sleep timer goes first:
        # «spegni/stop tra 30 minuti» contains transport words, but only counts
        # when its tail really parses as a duration — which is also why it is
        # NOT gated on is_play: «metti in pausa tra 30 minuti» carries a play
        # verb, and used to reach pause_explicit and pause the music at once.
        # The duration requirement is the guard a title needs.
        if not is_play and P["sleep_cancel"].search(t):
            return actions.cancel_sleep(self.lms)
        m = P["sleep"].search(t)
        if m:
            minutes = _parse_minutes(m.group(1))
            if minutes:
                return actions.set_sleep(self.lms, minutes)
        if P["pause_explicit"].search(t) or (not is_play and P["pause"].search(t)):
            return actions.pause(self.lms)
        # Bare "play" is a resume even though "play" is also a play verb.
        if P["resume_explicit"].match(t) or (not is_play and P["resume"].search(t)):
            return actions.resume(self.lms)
        if not is_play and P["next"].search(t):
            return actions.next_track(self.lms)
        if not is_play and P["prev"].search(t):
            return actions.previous_track(self.lms)
        # The loose forms («più forte», "louder") name no control, so a title
        # can be one: they only count when nothing asked to play something.
        if P["vol_up"].search(t) or (not is_play and P["vol_up_loose"].search(t)):
            return actions.change_volume(self.lms, "up")
        if P["vol_down"].search(t) or (not is_play and P["vol_down_loose"].search(t)):
            return actions.change_volume(self.lms, "down")
        # Gated by is_play so a title like "What Is This Feeling" still plays.
        if not is_play and P["nowplaying"].search(t):
            return actions.now_playing(self.lms)

        # 2) choose from the last read-out list by position. Accepts a digit or a
        # spoken number word ("la 2" / "the two", "numero tre" / "number three");
        # ASR gives words, not digits. The explicit forms answer even with no
        # open list (helpful hint); a bare numeral only counts as a pick while a
        # list is open, so it can't swallow an unrelated one-word command.
        m = P["choose_number"].match(t) or P["choose_article"].match(t)
        number = _as_number(m.group(1), ordinals=bool(self.candidates)) if m else None
        if number is None and self.candidates:
            bare = re.match(r"([a-z0-9]+)\s*$", t, re.I)
            number = _as_number(bare.group(1), ordinals=True) if bare else None
        if number is not None:
            # A pick from a room-opened list keeps playing in that room (unless
            # this very turn names another one — then self.lms already points
            # there and tagging is the caller's job).
            pick_lms, room_suffix = self.lms, ""
            if self.cand_player and not self._room_turn:
                pick_lms = self.lms.for_player(self.cand_player[0])
                room_suffix = msg("in_room", room=self.cand_player[1])
            picked = actions.choose_from(pick_lms, self.candidates, number,
                                         mode=self.cand_mode, guard=self._guard)
            if getattr(picked, "ok", False):
                self._used_list()
            return self._tag(
                self._tag(picked, _source_suffix(self.cand_source)),
                room_suffix)

        # 3) explicit source override phrases (win over the selector). Service
        # phrases route only the generic play_song; album/artist follow the
        # selector.
        m = P["local_prefix"].search(t)
        if m:
            return self._played(actions.play_local(self.lms, m.group(1).strip(),
                                                   guard=self._guard), "local")
        m = P["local_suffix"].search(t)
        if m:
            return self._played(actions.play_local(self.lms, m.group(1).strip(),
                                                   guard=self._guard), "local")
        for service in self.services:
            m = re.search(P["service"].format(s=_service_re(service)), t, re.I)
            if m:
                res = actions.play_song(self.lms.for_service(service),
                                        m.group(1).strip(), guard=self._guard)
                return self._played(self._tag(res, _source_suffix(service)), service)

        # 4) lists that open a numbered choice
        m = P["albums_list"].search(t)
        if m:  # "quali album ho di X" / "which albums do I have by X" -> local
            return self._remember(
                actions.local_albums_list(self.lms, m.group(1).strip(),
                                          guard=self._guard), "local")
        m = P["toptracks"].search(t)
        if m:  # top tracks -> streaming (selected or default service)
            return self._remember(
                actions.top_tracks_list(self._stream(source), m.group(1).strip(),
                                        guard=self._guard),
                self._stream_name(source))

        # 4b) name-based choice from the last read-out list (only while a list is
        # open). "metti Supernatural" / "play Supernatural" / bare "Supernatural"
        # -> the remembered candidate, never a fresh whole-library search.
        # choose_by_name returns None when nothing matches ("not a selection"),
        # so routing continues to the generic branches below.
        if self.candidates:
            m = P["name_pick"].match(t)
            if m:
                pick_lms, room_suffix = self.lms, ""
                if self.cand_player and not self._room_turn:
                    pick_lms = self.lms.for_player(self.cand_player[0])
                    room_suffix = msg("in_room", room=self.cand_player[1])
                chosen = actions.choose_by_name(
                    pick_lms, self.candidates, m.group(1).strip(),
                    mode=self.cand_mode, guard=self._guard
                )
                if chosen is not None:
                    if getattr(chosen, "ok", False):
                        self._used_list()
                    return self._tag(
                        self._tag(chosen, _source_suffix(self.cand_source)),
                        room_suffix)

        # 5) album — streaming or local per selector
        m = P["album"].search(t)
        if m:
            return self._resolve(m.group(1).strip(), actions.play_album, source)

        # 6) playlist (streaming: selected or default service)
        m = P["playlist"].search(t)
        if m:
            name = self._stream_name(source)
            return self._tag(
                actions.play_playlist(self.lms.for_service(name),
                                      m.group(1).strip(), guard=self._guard),
                _source_suffix(name))

        # 7) artist — streaming or local per selector
        m = P["artist"].search(t)
        if m:
            return self._resolve(m.group(1).strip(), actions.play_artist, source)

        # 8) generic play — streaming or local per selector. Steps 5-7 have
        # already declined, so only the generic branch may answer here — which
        # is why this does not go through ``_play_query``, and ``_play_query``
        # says so.
        m = P["generic_play"].search(t)
        if not m and "generic_play_suffix" in P:  # EN: "put Dark Side on"
            m = P["generic_play_suffix"].match(t)
        if m:
            return self._resolve(m.group(1).strip(), actions.play_song, source)

        self._unmatched = True
        return actions.ActionResult(msg("router_fallback"), ok=False)
