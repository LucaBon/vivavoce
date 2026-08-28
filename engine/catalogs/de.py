"""German message catalog — see ``it.py`` for the reference wording and
``__init__.py`` for the contract.

The polite form is deliberately absent: the app is addressed the way a
remote control is, so it says «du» throughout — the same register the
Italian catalog uses with «dimmi» and the English one with "your music".
"""

from __future__ import annotations

CODE = "de"
MESSAGES = {
    # -- shared errors / gates ---------------------------------------------
    "err_unreachable":
        "Ich erreiche die Anlage gerade nicht. Bitte versuch es gleich noch mal.",
    "blocked":
        "Das Lied gibt es, aber es steht auf der Sperrliste, also kann ich es "
        "nicht abspielen.",
    "not_owner": "Nur die Eltern d\u00fcrfen die Sperrliste \u00e4ndern.",
    "service_offline":
        "{service} ist nicht verbunden. \u00d6ffne die LMS-Einstellungen und "
        "melde dich neu an.",
    "no_service_online":
        "Es ist kein Streaming-Dienst verbunden. \u00d6ffne die "
        "LMS-Einstellungen und melde dich neu an.",

    # -- labels / list read-outs -------------------------------------------
    "generic_track": "Titel",
    "label_title_artist": "{title} von {artist}",
    "enum_item": "{n}: {name}",
    "didyoumean": "Ich habe mehrere f\u00fcr {query}. {listing}. Welches soll ich spielen?",

    # -- play (streaming) ----------------------------------------------------
    "ask_title": "Ich habe den Titel nicht verstanden. Kannst du das wiederholen?",
    "no_track_found": "Ich habe keinen Titel f\u00fcr {title} gefunden.",
    "no_track_by": "Ich habe {title} von {artist} nicht gefunden.",
    "playing": "Ich spiele {name}.",
    "playing_by": "Ich spiele {name} von {artist}.",
    "album_not_found": "Ich habe das Album {album} nicht gefunden.",
    "playing_track_from_album": "Ich spiele {title} aus dem Album {album}.",
    "track_not_in_album":
        "Ich habe {title} im Album {album} nicht gefunden; ich spiele das Album.",
    "playing_album": "Ich spiele das Album {album}.",
    "ask_album": "Ich habe nicht verstanden, welches Album. Kannst du das wiederholen?",
    "ask_artist": "Ich habe die Interpretin oder den Interpreten nicht verstanden. "
                  "Kannst du das wiederholen?",
    "artist_not_found": "Ich habe {artist} nicht gefunden.",
    "artist_unplayable": "Ich kann {artist} nicht abspielen.",
    "playing_artist": "Ich spiele Musik von {artist}.",
    "ask_playlist": "Ich habe nicht verstanden, welche Playlist. Kannst du das wiederholen?",
    "playlist_not_found": "Ich habe die Playlist {name} nicht gefunden.",
    "playing_playlist": "Ich spiele die Playlist {name}.",

    # -- queue (add to end / play next) --------------------------------------
    "queued": "Ich habe {name} zur Warteschlange hinzugef\u00fcgt.",
    "queued_by": "Ich habe {name} von {artist} zur Warteschlange hinzugef\u00fcgt.",
    "queued_next": "Ich spiele {name} gleich nach diesem Titel.",
    "queued_next_by": "Ich spiele {name} von {artist} gleich nach diesem Titel.",
    "playing_track_from_album_queued":
        "Ich habe {title} aus dem Album {album} zur Warteschlange hinzugef\u00fcgt.",
    "playing_track_from_album_queued_next":
        "Ich spiele {title} aus dem Album {album} gleich nach diesem Titel.",
    "track_not_in_album_queued":
        "Ich habe {title} im Album {album} nicht gefunden; ich habe das Album "
        "zur Warteschlange hinzugef\u00fcgt.",
    "track_not_in_album_queued_next":
        "Ich habe {title} im Album {album} nicht gefunden; ich spiele das Album "
        "gleich nach diesem Titel.",
    "playing_album_queued": "Ich habe das Album {album} zur Warteschlange hinzugef\u00fcgt.",
    "playing_album_queued_next": "Ich spiele das Album {album} gleich nach diesem Titel.",
    "playing_local_album_queued":
        "Ich habe das Album {title} aus deiner Musik zur Warteschlange hinzugef\u00fcgt.",
    "playing_local_album_queued_next":
        "Ich spiele das Album {title} aus deiner Musik gleich nach diesem Titel.",
    "playing_local_queued": "Ich habe {title} aus deiner Musik zur Warteschlange hinzugef\u00fcgt.",
    "playing_local_queued_next":
        "Ich spiele {title} aus deiner Musik gleich nach diesem Titel.",
    "queue_cleared": "Warteschlange geleert.",
    "queue_empty": "Die Warteschlange ist leer.",
    "queue_list": "In der Warteschlange: {listing}.",

    # -- favorites & radio ----------------------------------------------------
    "favorites_empty": "Du hast keine gespeicherten Favoriten.",
    "playing_favorites": "Ich spiele deine Favoriten.",
    "ask_radio": "Welchen Radiosender?",
    "radio_not_found":
        "Ich habe keinen Radiosender namens {name} in deinen Favoriten gefunden.",
    "playing_radio": "Ich spiele den Radiosender {name}.",

    # -- moods (vague requests \u2014 see engine/moods.py) -------------------------
    # See the Italian catalog: nothing was named, so nothing can be betrayed by
    # the choice \u2014 but the choice has to be said out loud, and taken back if
    # it misses. Neither miss quotes the request back, for the same reason.
    "playing_mood_genre":
        "Ich habe etwas {genre} aufgelegt. Sag was anderes, wenn es nicht passt.",
    "playing_mood_playlist":
        "Ich habe die Playlist {name} aufgelegt. Sag was anderes, wenn es nicht passt.",
    # A decade resolves to ONE year, not to the decade: that is what actually
    # started, so that is what gets said (see engine/moods.py).
    "playing_mood_year":
        "Ich habe etwas aus {year} aufgelegt. Sag was anderes, wenn es nicht passt.",
    "mood_not_found": "Ich habe in deiner Musik nichts Passendes gefunden.",
    "mood_exhausted": "Mir gehen die Ideen aus. Nenn mir am besten ein Genre.",

    # -- transport / info ----------------------------------------------------
    "paused": "Pausiert.",
    "resumed": "Ich spiele weiter.",
    "next_track": "N\u00e4chster Titel.",
    "previous_track": "Vorheriger Titel.",
    "volume_up": "Lauter.",
    "volume_down": "Leiser.",
    "ask_sleep": "Ich habe nicht verstanden, in wie vielen Minuten ich ausschalten "
                 "soll. Kannst du das wiederholen?",
    "sleep_set": "Alles klar, ich schalte in {minutes} Minuten aus.",
    "sleep_set_one": "Alles klar, ich schalte in einer Minute aus.",
    "sleep_too_long": "Das ist zu weit weg: Ich kann h\u00f6chstens in {max} Minuten "
                      "ausschalten.",
    "sleep_cancelled": "Schlaftimer abgebrochen.",
    "nothing_playing": "Gerade l\u00e4uft nichts.",
    "now_playing": "Gerade l\u00e4uft {title}.",
    "now_playing_by": "Gerade l\u00e4uft {title} von {artist}.",
    "paused_on": "Pausiert bei {title}.",
    "paused_on_by": "Pausiert bei {title} von {artist}.",

    # -- lists -> numbered choice -------------------------------------------
    "which_artist": "Von wem?",
    "no_tracks_for": "Ich habe keine Titel von {artist} gefunden.",
    "top_tracks": "Hier sind die meistgeh\u00f6rten Titel von {artist}. {listing}. "
                  "Welchen soll ich spielen?",
    "no_open_list":
        "Frag mich zuerst nach einer Liste, zum Beispiel: welche Titel gibt es "
        "von Pink Floyd.",
    "pick_range": "W\u00e4hl eine Zahl von 1 bis {n}.",

    # -- local library --------------------------------------------------------
    "ask_query": "Ich habe nicht verstanden, was ich spielen soll. Kannst du das "
                 "wiederholen?",
    "local_not_found": "Ich habe {query} in deiner Musik nicht gefunden.",
    "playing_local_album": "Ich spiele das Album {title} aus deiner Musik.",
    "playing_local": "Ich spiele {title} aus deiner Musik.",
    "local_no_artist": "Ich habe {artist} nicht in deiner Musik.",
    "local_no_albums": "Ich habe keine Alben von {artist} gefunden.",
    "local_albums": "Von {artist} habe ich: {listing}. Welches soll ich spielen?",

    # -- kid-safe blocklist ---------------------------------------------------
    "ask_block": "Ich habe nicht verstanden, was ich sperren soll. Kannst du das "
                 "wiederholen?",
    "already_blocked": "{term} steht schon auf der Sperrliste.",
    "blocklist_save_error":
        "Ich kann die Liste gerade nicht speichern. Bitte versuch es gleich noch mal.",
    "block_added": "Ok, ich habe {term} gesperrt.",
    "ask_unblock": "Ich habe nicht verstanden, was ich freigeben soll. Kannst du "
                   "das wiederholen?",
    "not_in_blocklist": "{term} steht nicht auf der Sperrliste.",
    "blocklist_update_error":
        "Ich kann die Liste gerade nicht aktualisieren. Bitte versuch es gleich "
        "noch mal.",
    "block_removed": "Ok, ich habe {term} freigegeben.",
    "blocklist_empty": "Die Sperrliste ist leer.",
    "blocklist_listing": "Gesperrte Titel: {terms}.",

    # -- web router (localvoice) ---------------------------------------------
    # Source tag appended to a play confirmation: with several sources the
    # reply must say which one answered.
    "from_service": " von {service}",
    "from_local": " aus deiner Musik",
    # Room tag appended when a command targets another player (\u00ab\u2026 in der
    # K\u00fcche\u00bb): {room} is the player\u2019s LMS name, spoken as-is.
    "in_room": " in {room}",
    # See the Italian catalog for why an overruled room still gets said.
    "read_as_title": " \u2014 ich habe das als Titel gelesen, es l\u00e4uft also hier",
    # See the Italian catalog for why this names the room and offers the way
    # out instead of reusing the shared ``pro_required``.
    "room_needs_pro":
        "Daf\u00fcr in {room} brauchst du Pro. "
        "Sag es ohne den Raum, dann mache ich es hier.",
    "heard_nothing": "Ich habe nichts geh\u00f6rt.",
    "router_fallback":
        "Das habe ich nicht verstanden. Versuch es mit: spiel, spiel das Album, "
        "aus meiner Musik, oder welche Alben habe ich von.",
    "internal_error": "Interner Fehler: {error}",
    "pro_required":
        "Das ist eine Pro-Funktion: Du schaltest sie in den Einstellungen der "
        "Seite frei.",
}
