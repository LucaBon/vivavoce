"""English message catalog — see ``it.py`` for the reference wording and
``__init__.py`` for the contract.
"""

from __future__ import annotations

CODE = "en"
MESSAGES = {
    # -- shared errors / gates ---------------------------------------------
    "err_unreachable":
        "I can't reach the system right now. Please try again in a moment.",
    "blocked":
        "That song exists, but it's on the blocked-songs list, so I can't "
        "play it.",
    "not_owner": "Only the parent can change the blocked-songs list.",

    # -- labels / list read-outs -------------------------------------------
    "generic_track": "track",
    "label_title_artist": "{title} by {artist}",
    "enum_item": "{n}: {name}",
    "didyoumean": "I found several for {query}. {listing}. Which one should I play?",

    # -- play (streaming) ----------------------------------------------------
    "ask_title": "I didn't catch the title. Can you repeat?",
    "no_track_found": "I couldn't find any track for {title}.",
    "no_track_by": "I couldn't find {title} by {artist}.",
    "playing": "Playing {name}.",
    "playing_by": "Playing {name} by {artist}.",
    "album_not_found": "I couldn't find the album {album}.",
    "playing_track_from_album": "Playing {title} from the album {album}.",
    "track_not_in_album":
        "I couldn't find {title} in the album {album}; playing the album.",
    "playing_album": "Playing the album {album}.",
    "ask_album": "I didn't catch which album. Can you repeat?",
    "ask_artist": "I didn't catch the artist. Can you repeat?",
    "artist_not_found": "I couldn't find the artist {artist}.",
    "artist_unplayable": "I can't play the artist {artist}.",
    "playing_artist": "Playing music by {artist}.",
    "ask_playlist": "I didn't catch which playlist. Can you repeat?",
    "playlist_not_found": "I couldn't find the playlist {name}.",
    "playing_playlist": "Playing the playlist {name}.",

    # -- queue (add to end / play next) --------------------------------------
    "queued": "Added {name} to the queue.",
    "queued_by": "Added {name} by {artist} to the queue.",
    "queued_next": "I'll play {name} right after this one.",
    "queued_next_by": "I'll play {name} by {artist} right after this one.",
    "playing_track_from_album_queued":
        "Added {title} from the album {album} to the queue.",
    "playing_track_from_album_queued_next":
        "I'll play {title} from the album {album} right after this one.",
    "track_not_in_album_queued":
        "I couldn't find {title} in the album {album}; added the album to the queue.",
    "track_not_in_album_queued_next":
        "I couldn't find {title} in the album {album}; I'll play the album right after this one.",
    "playing_album_queued": "Added the album {album} to the queue.",
    "playing_album_queued_next": "I'll play the album {album} right after this one.",
    "playing_local_album_queued":
        "Added the album {title} from your music to the queue.",
    "playing_local_album_queued_next":
        "I'll play the album {title} from your music right after this one.",
    "playing_local_queued": "Added {title} from your music to the queue.",
    "playing_local_queued_next":
        "I'll play {title} from your music right after this one.",
    "queue_cleared": "Queue cleared.",
    "queue_empty": "The queue is empty.",
    "queue_list": "Coming up: {listing}.",

    # -- favorites & radio ----------------------------------------------------
    "favorites_empty": "You don't have any saved favorites.",
    "playing_favorites": "Playing your favorites.",
    "ask_radio": "Which radio station?",
    "radio_not_found":
        "I couldn't find a radio station called {name} among your favorites.",
    "playing_radio": "Playing the radio station {name}.",

    # -- moods (vague requests — see engine/moods.py) -------------------------
    "playing_mood_genre":
        "I've put on some {genre}. Say another one if it doesn't fit.",
    "playing_mood_playlist":
        "I've put on the {name} playlist. Say another one if it doesn't fit.",
    "playing_mood_year":
        "I've put on something from {year}. Say another one if it doesn't fit.",
    "mood_not_found": "I couldn't find anything that fits in your music.",
    "mood_exhausted": "I'm out of ideas. Try naming a genre.",

    # -- transport / info ----------------------------------------------------
    "paused": "Paused.",
    "resumed": "Resuming playback.",
    "next_track": "Next track.",
    "previous_track": "Previous track.",
    "volume_up": "Volume up.",
    "volume_down": "Volume down.",
    "ask_sleep": "I didn't catch in how many minutes to stop. Can you repeat?",
    "sleep_set": "Okay, stopping in {minutes} minutes.",
    "sleep_set_one": "Okay, stopping in one minute.",
    "sleep_too_long": "That's too far off: I can stop in at most {max} minutes.",
    "sleep_cancelled": "Sleep timer cancelled.",
    "nothing_playing": "Nothing is playing right now.",
    "now_playing": "Now playing {title}.",
    "now_playing_by": "Now playing {title} by {artist}.",
    "paused_on": "Paused on {title}.",
    "paused_on_by": "Paused on {title} by {artist}.",

    # -- lists -> numbered choice -------------------------------------------
    "which_artist": "Which artist?",
    "no_tracks_for": "I couldn't find tracks for {artist}.",
    "top_tracks": "Here are the most played tracks by {artist}. {listing}. Which one should I play?",
    "no_open_list":
        "First ask me for a list, for example: which are the top tracks by Pink Floyd.",
    "pick_range": "Pick a number from 1 to {n}.",

    # -- local library --------------------------------------------------------
    "ask_query": "I didn't catch what to play. Can you repeat?",
    "local_not_found": "I couldn't find {query} in your music.",
    "playing_local_album": "Playing the album {title} from your music.",
    "playing_local": "Playing {title} from your music.",
    "local_no_artist": "I don't have {artist} in your music.",
    "local_no_albums": "I couldn't find albums by {artist}.",
    "local_albums": "By {artist} I have: {listing}. Which one should I play?",

    # -- kid-safe blocklist ---------------------------------------------------
    "ask_block": "I didn't catch what to block. Can you repeat?",
    "already_blocked": "{term} is already in the blocked-songs list.",
    "blocklist_save_error":
        "I can't save the list right now. Please try again in a moment.",
    "block_added": "Ok, I blocked {term}.",
    "ask_unblock": "I didn't catch what to unblock. Can you repeat?",
    "not_in_blocklist": "{term} is not in the blocked-songs list.",
    "blocklist_update_error":
        "I can't update the list right now. Please try again in a moment.",
    "block_removed": "Ok, I unblocked {term}.",
    "blocklist_empty": "The blocked-songs list is empty.",
    "blocklist_listing": "Blocked songs: {terms}.",

    # -- web router (localvoice) ---------------------------------------------
    # Source tag appended to a play confirmation: with three sources (local,
    # TIDAL, Qobuz) the reply must say which one answered.
    "from_service": " from {service}",
    "from_local": " from your music",
    # Room tag appended when a command targets another player ("… in the
    # kitchen"): {room} is the player's LMS name, spoken as-is.
    "in_room": " in {room}",
    # See the Italian catalog for why an overruled room still gets said.
    "read_as_title": " — I read that as a title, so it's playing here",
    # See the Italian catalog for why this names the room and offers the way
    # out instead of reusing the shared ``pro_required``.
    "room_needs_pro":
        "Doing that in {room} needs Pro. "
        "Say it without the room and I'll do it here.",
    "heard_nothing": "I didn't hear anything.",
    "router_fallback":
        "I didn't understand. Try: play, play the album, from my music, "
        "or which albums do I have by.",
    "internal_error": "Internal error: {error}",
    "pro_required":
        "This is a Pro feature: activate it from the page settings.",
}
