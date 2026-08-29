"""French message catalog — see ``it.py`` for the reference wording and
``__init__.py`` for the contract.
"""

from __future__ import annotations

CODE = "fr"
MESSAGES = {
    # -- shared errors / gates ---------------------------------------------
    "err_unreachable":
        "Je n'arrive pas à joindre le système pour le moment. "
        "Réessaie dans un instant.",
    "blocked":
        "Ce morceau existe, mais il est dans la liste des morceaux bloqués, "
        "donc je ne peux pas le jouer.",
    "not_owner":
        "Seul un parent peut modifier la liste des morceaux bloqués.",
    "service_offline":
        "{service} n'est pas connect\u00e9. Ouvre les r\u00e9glages de LMS et "
        "reconnecte-toi.",
    "no_service_online":
        "Aucun service de streaming n'est connect\u00e9. Ouvre les r\u00e9glages "
        "de LMS et reconnecte-toi.",

    # A row the library HAS and cannot play. A streaming plugin imports its
    # favourites INTO the LMS library: the row answers a local search, carries a
    # library id and queues without complaint, and its audio is still
    # ``tidal://`` — silent for as long as the plugin is logged out. Naming the
    # service is the whole point of the sentence: "I didn't find it" would be a
    # lie about the library, and "it won't play" would leave nobody anything to
    # do about it. The offer that follows is put together in
    # ``sources.SourceChoice``, which is where a request finds out which other
    # service is connected.
    "local_import_offline":
        "Ce que j'ai de {query} dans ta musique vient de {service}, qui n'est "
        "pas connect\u00e9.",
    "service_not_connected": "{service} n'est pas connect\u00e9.",
    "offer_play_from": "Tu veux que je le mette depuis {service} ?",
    # The two buttons the web app puts under an offer, and the words it
    # sends when one is tapped: they have to be answers the language pack's
    # ``yes``/``no`` patterns actually parse, because tapping is typing.
    "offer_yes": "Oui",
    "offer_no": "Non",
    "offer_declined": "D'accord.",

    # -- labels / list read-outs -------------------------------------------
    "generic_track": "morceau",
    "label_title_artist": "{title} de {artist}",
    "enum_item": "{n} : {name}",
    "didyoumean":
        "J'en ai trouvé plusieurs pour {query}. {listing}. Lequel je mets ?",

    # -- play (streaming) ----------------------------------------------------
    "ask_title": "Je n'ai pas saisi le titre. Tu peux répéter ?",
    "no_track_found": "Je n'ai trouvé aucun morceau pour {title}.",
    "no_track_by": "Je n'ai pas trouvé {title} de {artist}.",
    "playing": "Je mets {name}.",
    "playing_by": "Je mets {name} de {artist}.",
    "album_not_found": "Je n'ai pas trouvé l'album {album}.",
    "playing_track_from_album": "Je mets {title} de l'album {album}.",
    "track_not_in_album":
        "Je n'ai pas trouvé {title} dans l'album {album} ; je mets l'album.",
    "playing_album": "Je mets l'album {album}.",
    "ask_album": "Je n'ai pas saisi quel album. Tu peux répéter ?",
    "ask_artist": "Je n'ai pas saisi l'artiste. Tu peux répéter ?",
    "artist_not_found": "Je n'ai pas trouvé l'artiste {artist}.",
    "artist_unplayable": "Je ne peux pas jouer l'artiste {artist}.",
    "playing_artist": "Je mets la musique de {artist}.",
    "ask_playlist": "Je n'ai pas saisi quelle playlist. Tu peux répéter ?",
    "playlist_not_found": "Je n'ai pas trouvé la playlist {name}.",
    "playing_playlist": "Je mets la playlist {name}.",

    # -- queue (add to end / play next) --------------------------------------
    "queued": "J'ai ajouté {name} à la file d'attente.",
    "queued_by": "J'ai ajouté {name} de {artist} à la file d'attente.",
    "queued_next": "Je mets {name} juste après celle-là.",
    "queued_next_by": "Je mets {name} de {artist} juste après celle-là.",
    "playing_track_from_album_queued":
        "J'ai ajouté {title} de l'album {album} à la file d'attente.",
    "playing_track_from_album_queued_next":
        "Je mets {title} de l'album {album} juste après celle-là.",
    "track_not_in_album_queued":
        "Je n'ai pas trouvé {title} dans l'album {album} ; "
        "j'ai ajouté l'album à la file d'attente.",
    "track_not_in_album_queued_next":
        "Je n'ai pas trouvé {title} dans l'album {album} ; "
        "je mets l'album juste après celle-là.",
    "playing_album_queued": "J'ai ajouté l'album {album} à la file d'attente.",
    "playing_album_queued_next": "Je mets l'album {album} juste après celle-là.",
    "playing_local_album_queued":
        "J'ai ajouté l'album {title} de ta musique à la file d'attente.",
    "playing_local_album_queued_next":
        "Je mets l'album {title} de ta musique juste après celle-là.",
    "playing_local_queued":
        "J'ai ajouté {title} de ta musique à la file d'attente.",
    "playing_local_queued_next":
        "Je mets {title} de ta musique juste après celle-là.",
    "queue_cleared": "File d'attente vidée.",
    "queue_empty": "La file d'attente est vide.",
    "queue_list": "À suivre : {listing}.",

    # -- favorites & radio ----------------------------------------------------
    "favorites_empty": "Tu n'as aucun favori enregistré.",
    "playing_favorites": "Je mets tes favoris.",
    "ask_radio": "Quelle station de radio ?",
    "radio_not_found":
        "Je n'ai pas trouvé de station de radio appelée {name} dans tes favoris.",
    "playing_radio": "Je mets la station {name}.",

    # -- moods (vague requests — see engine/moods.py) -------------------------
    "playing_mood_genre":
        "J'ai mis du {genre}. Dis-m'en une autre si ça ne va pas.",
    "playing_mood_playlist":
        "J'ai mis la playlist {name}. Dis-m'en une autre si ça ne va pas.",
    "playing_mood_year":
        "J'ai mis quelque chose de {year}. Dis-m'en une autre si ça ne va pas.",
    "mood_not_found": "Je n'ai rien trouvé qui convienne dans ta musique.",
    "mood_exhausted": "Je suis à court d'idées. Essaie de nommer un genre.",

    # -- transport / info ----------------------------------------------------
    "paused": "En pause.",
    "resumed": "Je reprends la lecture.",
    "next_track": "Morceau suivant.",
    "previous_track": "Morceau précédent.",
    "volume_up": "Je monte le son.",
    "volume_down": "Je baisse le son.",
    "ask_sleep":
        "Je n'ai pas saisi dans combien de minutes arrêter. Tu peux répéter ?",
    "sleep_set": "D'accord, j'arrête dans {minutes} minutes.",
    "sleep_set_one": "D'accord, j'arrête dans une minute.",
    "sleep_too_long":
        "C'est trop loin : je peux arrêter dans {max} minutes au maximum.",
    "sleep_cancelled": "Minuterie annulée.",
    "nothing_playing": "Rien ne joue en ce moment.",
    "now_playing": "En ce moment : {title}.",
    "now_playing_by": "En ce moment : {title} de {artist}.",
    "paused_on": "En pause sur {title}.",
    "paused_on_by": "En pause sur {title} de {artist}.",

    # -- lists -> numbered choice -------------------------------------------
    "which_artist": "Quel artiste ?",
    "no_tracks_for": "Je n'ai pas trouvé de morceaux de {artist}.",
    "top_tracks":
        "Voici les morceaux les plus écoutés de {artist}. {listing}. "
        "Lequel je mets ?",
    "no_open_list":
        "Demande-moi d'abord une liste, par exemple : quels sont les "
        "meilleurs morceaux de Pink Floyd.",
    "pick_range": "Choisis un numéro entre 1 et {n}.",

    # -- local library --------------------------------------------------------
    "ask_query": "Je n'ai pas saisi quoi mettre. Tu peux répéter ?",
    "local_not_found": "Je n'ai pas trouvé {query} dans ta musique.",
    "playing_local_album": "Je mets l'album {title} de ta musique.",
    "playing_local": "Je mets {title} de ta musique.",
    "local_no_artist": "Je n'ai pas {artist} dans ta musique.",
    "local_no_albums": "Je n'ai pas trouvé d'albums de {artist}.",
    "local_albums": "De {artist} j'ai : {listing}. Lequel je mets ?",

    # -- kid-safe blocklist ---------------------------------------------------
    "ask_block": "Je n'ai pas saisi quoi bloquer. Tu peux répéter ?",
    "already_blocked": "{term} est déjà dans la liste des morceaux bloqués.",
    "blocklist_save_error":
        "Je n'arrive pas à enregistrer la liste pour le moment. "
        "Réessaie dans un instant.",
    "block_added": "Ok, j'ai bloqué {term}.",
    "ask_unblock": "Je n'ai pas saisi quoi débloquer. Tu peux répéter ?",
    "not_in_blocklist": "{term} n'est pas dans la liste des morceaux bloqués.",
    "blocklist_update_error":
        "Je n'arrive pas à mettre à jour la liste pour le moment. "
        "Réessaie dans un instant.",
    "block_removed": "Ok, j'ai débloqué {term}.",
    "blocklist_empty": "La liste des morceaux bloqués est vide.",
    "blocklist_listing": "Morceaux bloqués : {terms}.",

    # -- web router (localvoice) ---------------------------------------------
    # Source tag appended to a play confirmation: with three sources (local,
    # TIDAL, Qobuz) the reply must say which one answered.
    "from_service": " sur {service}",
    "from_local": " de ta musique",
    # Room tag appended when a command targets another player ("… dans la
    # cuisine"): {room} is the player's LMS name, spoken as-is.
    "in_room": " dans {room}",
    # See the Italian catalog for why an overruled room still gets said.
    "read_as_title": " — je l'ai lu comme un titre, donc ça joue ici",
    # See the Italian catalog for why this names the room and offers the way
    # out instead of reusing the shared ``pro_required``.
    "room_needs_pro":
        "Faire ça dans {room} demande la version Pro. "
        "Dis-le sans la pièce et je le fais ici.",
    "heard_nothing": "Je n'ai rien entendu.",
    "router_fallback":
        "Je n'ai pas compris. Essaie : mets, mets l'album, de ma musique, "
        "ou quels albums j'ai de.",
    "internal_error": "Erreur interne : {error}",
    "pro_required":
        "C'est une fonction Pro : active-la dans les réglages de la page.",
}
