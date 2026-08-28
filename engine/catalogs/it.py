"""Italian message catalog — the reference wording.

Every string the product says out loud in Italian, keyed by id. The
contract is in ``__init__.py``: a module here declares ``CODE`` and
``MESSAGES`` and the registry finds it by itself.
"""

from __future__ import annotations

CODE = "it"
MESSAGES = {
    # -- shared errors / gates ---------------------------------------------
    "err_unreachable":
        "Non riesco a contattare l'impianto in questo momento. Riprova tra poco.",
    "blocked":
        "Questa canzone c'è, ma è nella lista dei brani bloccati, quindi non "
        "posso metterla.",
    "not_owner": "Solo il genitore può cambiare la lista dei brani bloccati.",
    # A streaming request that never reached a search: the plugin is
    # installed but logged out (see LMSClient.can_search). Saying "non ho
    # trovato nessun brano" here is a lie about the music library — nobody
    # was asked. Both name the fix, because it is one the user can act on.
    "service_offline":
        "{service} non \u00e8 collegato. Apri le impostazioni di LMS e "
        "rifai l'accesso.",
    "no_service_online":
        "Nessun servizio di streaming \u00e8 collegato. Apri le impostazioni "
        "di LMS e rifai l'accesso.",

    # -- labels / list read-outs -------------------------------------------
    "generic_track": "brano",
    "label_title_artist": "{title} di {artist}",
    "enum_item": "{n}: {name}",
    "didyoumean": "Ne ho diversi per {query}. {listing}. Quale metto?",

    # -- play (streaming) ----------------------------------------------------
    "ask_title": "Non ho capito il titolo. Puoi ripetere?",
    "no_track_found": "Non ho trovato nessun brano per {title}.",
    "no_track_by": "Non ho trovato {title} di {artist}.",
    "playing": "Riproduco {name}.",
    "playing_by": "Riproduco {name} di {artist}.",
    "album_not_found": "Non ho trovato l'album {album}.",
    "playing_track_from_album": "Riproduco {title} dall'album {album}.",
    "track_not_in_album":
        "Non ho trovato {title} nell'album {album}; riproduco l'album.",
    "playing_album": "Riproduco l'album {album}.",
    "ask_album": "Non ho capito quale album. Puoi ripetere?",
    "ask_artist": "Non ho capito l'artista. Puoi ripetere?",
    "artist_not_found": "Non ho trovato l'artista {artist}.",
    "artist_unplayable": "Non riesco a riprodurre l'artista {artist}.",
    "playing_artist": "Riproduco la musica di {artist}.",
    "ask_playlist": "Non ho capito quale playlist. Puoi ripetere?",
    "playlist_not_found": "Non ho trovato la playlist {name}.",
    "playing_playlist": "Riproduco la playlist {name}.",

    # -- queue (add to end / play next) --------------------------------------
    "queued": "Ho aggiunto {name} alla coda.",
    "queued_by": "Ho aggiunto {name} di {artist} alla coda.",
    "queued_next": "Metto {name} subito dopo questa.",
    "queued_next_by": "Metto {name} di {artist} subito dopo questa.",
    "playing_track_from_album_queued":
        "Ho aggiunto {title} dall'album {album} alla coda.",
    "playing_track_from_album_queued_next":
        "Metto {title} dall'album {album} subito dopo questa.",
    "track_not_in_album_queued":
        "Non ho trovato {title} nell'album {album}; ho aggiunto l'album alla coda.",
    "track_not_in_album_queued_next":
        "Non ho trovato {title} nell'album {album}; metto l'album subito dopo questa.",
    "playing_album_queued": "Ho aggiunto l'album {album} alla coda.",
    "playing_album_queued_next": "Metto l'album {album} subito dopo questa.",
    "playing_local_album_queued":
        "Ho aggiunto l'album {title} alla coda dalla tua musica.",
    "playing_local_album_queued_next":
        "Metto l'album {title} dalla tua musica subito dopo questa.",
    "playing_local_queued": "Ho aggiunto {title} alla coda dalla tua musica.",
    "playing_local_queued_next": "Metto {title} dalla tua musica subito dopo questa.",
    "queue_cleared": "Coda svuotata.",
    "queue_empty": "La coda è vuota.",
    "queue_list": "In coda: {listing}.",

    # -- favorites & radio ----------------------------------------------------
    "favorites_empty": "Non hai preferiti salvati.",
    "playing_favorites": "Riproduco i preferiti.",
    "ask_radio": "Quale radio?",
    "radio_not_found":
        "Non ho trovato una radio chiamata {name} tra i tuoi preferiti.",
    "playing_radio": "Metto la radio {name}.",

    # -- moods (vague requests — see engine/moods.py) -------------------------
    # Nothing was named, so nothing can be betrayed by the choice — but the
    # choice has to be said out loud, and taken back if it misses.
    #
    # The two misses deliberately do NOT quote the request back. The spoken
    # tail is whatever the listener said, and half the vocabulary already
    # carries its own preposition: "per cena" in a frame ending in "per"
    # reads «Ho finito le idee per per cena». There is no frame that survives
    # every tail, and echoing adds nothing they did not just say.
    "playing_mood_genre": "Ho messo un po' di {genre}. Se non va, dimmi un'altra.",
    "playing_mood_playlist":
        "Ho messo la playlist {name}. Se non va, dimmi un'altra.",
    # A decade resolves to ONE year, not to the decade: that is what actually
    # started, so that is what gets said (see engine/moods.py).
    "playing_mood_year":
        "Ho messo qualcosa del {year}. Se non va, dimmi un'altra.",
    "mood_not_found": "Non ho trovato niente che vada bene nella tua musica.",
    "mood_exhausted": "Ho finito le idee. Prova a dirmi un genere.",

    # -- transport / info ----------------------------------------------------
    "paused": "In pausa.",
    "resumed": "Riprendo la riproduzione.",
    "next_track": "Brano successivo.",
    "previous_track": "Brano precedente.",
    "volume_up": "Volume alzato.",
    "volume_down": "Volume abbassato.",
    "ask_sleep": "Non ho capito tra quanti minuti spegnere. Puoi ripetere?",
    "sleep_set": "Va bene, spengo tra {minutes} minuti.",
    "sleep_set_one": "Va bene, spengo tra un minuto.",
    "sleep_too_long": "\u00c8 troppo: posso spegnere al massimo tra {max} minuti.",
    "sleep_cancelled": "Timer di spegnimento annullato.",
    "nothing_playing": "Al momento non sta suonando niente.",
    "now_playing": "Sta suonando {title}.",
    "now_playing_by": "Sta suonando {title} di {artist}.",
    "paused_on": "\u00c8 in pausa su {title}.",
    "paused_on_by": "\u00c8 in pausa su {title} di {artist}.",

    # -- lists -> numbered choice -------------------------------------------
    "which_artist": "Di quale artista?",
    "no_tracks_for": "Non ho trovato brani per {artist}.",
    "top_tracks": "Ecco i brani più ascoltati di {artist}. {listing}. Quale metto?",
    "no_open_list":
        "Prima chiedimi un elenco, ad esempio: quali sono i brani di Pink Floyd.",
    "pick_range": "Scegli un numero da 1 a {n}.",

    # -- local library --------------------------------------------------------
    "ask_query": "Non ho capito cosa mettere. Puoi ripetere?",
    "local_not_found": "Non ho trovato {query} nella tua musica.",
    "playing_local_album": "Riproduco l'album {title} dalla tua musica.",
    "playing_local": "Riproduco {title} dalla tua musica.",
    "local_no_artist": "Non ho {artist} nella tua musica.",
    "local_no_albums": "Non ho trovato album di {artist}.",
    "local_albums": "Di {artist} ho: {listing}. Quale metto?",

    # -- kid-safe blocklist ---------------------------------------------------
    "ask_block": "Non ho capito cosa bloccare. Puoi ripetere?",
    "already_blocked": "{term} è già nella lista dei brani bloccati.",
    "blocklist_save_error":
        "Non riesco a salvare la lista in questo momento. Riprova tra poco.",
    "block_added": "Ok, ho bloccato {term}.",
    "ask_unblock": "Non ho capito cosa sbloccare. Puoi ripetere?",
    "not_in_blocklist": "{term} non è nella lista dei brani bloccati.",
    "blocklist_update_error":
        "Non riesco ad aggiornare la lista in questo momento. Riprova tra poco.",
    "block_removed": "Ok, ho sbloccato {term}.",
    "blocklist_empty": "La lista dei brani bloccati è vuota.",
    "blocklist_listing": "Brani bloccati: {terms}.",

    # -- web router (localvoice) ---------------------------------------------
    # Source tag appended to a play confirmation: with three sources (local,
    # TIDAL, Qobuz) the reply must say which one answered.
    "from_service": " da {service}",
    "from_local": " dalla tua musica",
    # Room tag appended when a command targets another player («… in cucina»):
    # {room} is the player's LMS name, spoken as-is.
    "in_room": " in {room}",
    # The room was heard and then overruled: the library says these words name
    # a record, not a place. Only Pro ever gets this — without it the room
    # would have been refused anyway, so there is nothing to explain. It has to
    # be said out loud for the reason T2.7a exists: a room the listener spoke
    # cannot just disappear from the answer, or a wrong guess is invisible
    # exactly where it costs the most.
    "read_as_title": " — l'ho preso come titolo, quindi suona qui",
    # Same situation, no Pro. Its own key rather than the shared
    # ``pro_required`` — which also answers kid-safe — because this reply has
    # three jobs that a generic Pro wall cannot do.
    #
    # It NAMES THE ROOM, and that is the load-bearing part: a room name is
    # only ever a guess about what the words meant, so saying it out loud is
    # what makes a wrong guess visible. «metti breakfast in america» on a
    # system with a player called «America» answers «per farlo in America
    # serve Pro» — and the listener knows instantly what went wrong, where the
    # generic string hid it completely.
    #
    # It offers the one-turn way out, which is what makes refusing cheap for
    # whoever is talking: a dead end becomes a retry.
    #
    # «farlo»/«lo faccio», not «metterlo»: this fires BEFORE routing, so
    # nobody knows yet whether the phrase was a play or a pause, and the
    # sentence has to hold for both. Two short sentences on purpose — the
    # reply is read aloud.
    "room_needs_pro":
        "Per farlo in {room} serve Pro. "
        "Dillo senza la stanza e lo faccio qui.",
    "heard_nothing": "Non ho sentito niente.",
    "router_fallback":
        "Non ho capito. Prova con: riproduci, metti l'album, dalla mia musica, "
        "oppure quali album ho di.",
    "internal_error": "Errore interno: {error}",
    "pro_required":
        "Questa è una funzione Pro: si attiva dalle impostazioni della pagina.",
}
