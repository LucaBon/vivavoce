"""Spanish message catalog — see ``it.py`` for the reference wording and
``__init__.py`` for the contract.

Peninsular Spanish, because the page has offered ``es-ES`` to the microphone
since read-back shipped and the voice it picks for the reply is the one that
tag names. The *patterns* in ``localvoice/lang/es.py`` accept the Latin
American phrasings too — «poné», «coloca» — because accepting an extra verb
costs nothing; a reply has to be written in one variety or another, and this is
the one the voice speaks.
"""

from __future__ import annotations

CODE = "es"
MESSAGES = {
    # -- shared errors / gates ---------------------------------------------
    "err_unreachable":
        "No consigo conectar con el equipo en este momento. "
        "Inténtalo de nuevo en un momento.",
    "blocked":
        "Esta canción existe, pero está en la lista de temas "
        "bloqueados, así que no puedo ponerla.",
    "not_owner":
        "Solo un padre o una madre puede cambiar la lista de temas bloqueados.",
    "service_offline":
        "{service} no está conectado. Abre los ajustes de LMS y "
        "vuelve a iniciar sesión.",
    "no_service_online":
        "No hay ningún servicio de streaming conectado. Abre los ajustes "
        "de LMS y vuelve a iniciar sesión.",

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
        "Lo que tengo de {query} en tu música viene de {service}, que no "
        "está conectado.",
    "service_not_connected": "{service} no está conectado.",
    "offer_play_from": "¿Quieres que la ponga desde {service}?",
    # The two buttons the web app puts under an offer, and the words it
    # sends when one is tapped: they have to be answers the language pack's
    # ``yes``/``no`` patterns actually parse, because tapping is typing.
    "offer_yes": "Sí",
    "offer_no": "No",
    "offer_declined": "Vale.",

    # -- labels / list read-outs -------------------------------------------
    "generic_track": "tema",
    "label_title_artist": "{title} de {artist}",
    "enum_item": "{n}: {name}",
    "didyoumean": "Tengo varias de {query}. {listing}. ¿Cuál pongo?",

    # -- play (streaming) ----------------------------------------------------
    "ask_title": "No he entendido el título. ¿Puedes repetirlo?",
    "no_track_found": "No he encontrado ningún tema de {title}.",
    "no_track_by": "No he encontrado {title} de {artist}.",
    "playing": "Pongo {name}.",
    "playing_by": "Pongo {name} de {artist}.",
    "album_not_found": "No he encontrado el álbum {album}.",
    "playing_track_from_album": "Pongo {title} del álbum {album}.",
    "track_not_in_album":
        "No he encontrado {title} en el álbum {album}; pongo el álbum.",
    "playing_album": "Pongo el álbum {album}.",
    "ask_album": "No he entendido qué álbum. ¿Puedes repetirlo?",
    "ask_artist": "No he entendido el artista. ¿Puedes repetirlo?",
    "artist_not_found": "No he encontrado al artista {artist}.",
    "artist_unplayable": "No puedo reproducir al artista {artist}.",
    "playing_artist": "Pongo la música de {artist}.",
    "ask_playlist": "No he entendido qué lista. ¿Puedes repetirlo?",
    "playlist_not_found": "No he encontrado la lista {name}.",
    "playing_playlist": "Pongo la lista {name}.",

    # -- queue (add to end / play next) --------------------------------------
    "queued": "He añadido {name} a la cola.",
    "queued_by": "He añadido {name} de {artist} a la cola.",
    "queued_next": "Pongo {name} justo después de esta.",
    "queued_next_by": "Pongo {name} de {artist} justo después de esta.",
    "playing_track_from_album_queued":
        "He añadido {title} del álbum {album} a la cola.",
    "playing_track_from_album_queued_next":
        "Pongo {title} del álbum {album} justo después de esta.",
    "track_not_in_album_queued":
        "No he encontrado {title} en el álbum {album}; "
        "he añadido el álbum a la cola.",
    "track_not_in_album_queued_next":
        "No he encontrado {title} en el álbum {album}; "
        "pongo el álbum justo después de esta.",
    "playing_album_queued": "He añadido el álbum {album} a la cola.",
    "playing_album_queued_next":
        "Pongo el álbum {album} justo después de esta.",
    "playing_local_album_queued":
        "He añadido el álbum {title} de tu música a la cola.",
    "playing_local_album_queued_next":
        "Pongo el álbum {title} de tu música justo después de esta.",
    "playing_local_queued": "He añadido {title} de tu música a la cola.",
    "playing_local_queued_next":
        "Pongo {title} de tu música justo después de esta.",
    "queue_cleared": "Cola vaciada.",
    "queue_empty": "La cola está vacía.",
    "queue_list": "En la cola: {listing}.",

    # -- favorites & radio ----------------------------------------------------
    "favorites_empty": "No tienes favoritos guardados.",
    "playing_favorites": "Pongo tus favoritos.",
    "ask_radio": "¿Qué emisora?",
    "radio_not_found":
        "No he encontrado ninguna emisora llamada {name} entre tus favoritos.",
    "playing_radio": "Pongo la emisora {name}.",

    # -- moods (vague requests — see engine/moods.py) -------------------------
    # See the Italian catalog for why the two misses do not quote the request
    # back: the spoken tail carries its own preposition half the time, and
    # «para cenar» inside a frame ending in "para" reads twice.
    "playing_mood_genre":
        "He puesto un poco de {genre}. Si no te va, dime otra.",
    "playing_mood_playlist":
        "He puesto la lista {name}. Si no te va, dime otra.",
    # A decade resolves to ONE year, not to the decade: that is what actually
    # started, so that is what gets said (see engine/moods.py).
    "playing_mood_year":
        "He puesto algo de {year}. Si no te va, dime otra.",
    "mood_not_found": "No he encontrado nada que encaje en tu música.",
    "mood_exhausted": "Se me han acabado las ideas. Prueba a decirme un género.",

    # -- transport / info ----------------------------------------------------
    "paused": "En pausa.",
    "resumed": "Sigo con la reproducción.",
    "next_track": "Siguiente tema.",
    "previous_track": "Tema anterior.",
    "volume_up": "Subo el volumen.",
    "volume_down": "Bajo el volumen.",
    "ask_sleep":
        "No he entendido dentro de cuántos minutos apagar. "
        "¿Puedes repetirlo?",
    "sleep_set": "Vale, apago dentro de {minutes} minutos.",
    "sleep_set_one": "Vale, apago dentro de un minuto.",
    "sleep_too_long":
        "Es demasiado: como mucho puedo apagar dentro de {max} minutos.",
    "sleep_cancelled": "Temporizador cancelado.",
    "nothing_playing": "Ahora mismo no está sonando nada.",
    "now_playing": "Está sonando {title}.",
    "now_playing_by": "Está sonando {title} de {artist}.",
    "paused_on": "Está en pausa en {title}.",
    "paused_on_by": "Está en pausa en {title} de {artist}.",

    # -- lists -> numbered choice -------------------------------------------
    "which_artist": "¿De qué artista?",
    "no_tracks_for": "No he encontrado temas de {artist}.",
    "top_tracks":
        "Estos son los temas más escuchados de {artist}. {listing}. "
        "¿Cuál pongo?",
    "no_open_list":
        "Pídeme antes una lista, por ejemplo: cuáles son los mejores "
        "temas de Pink Floyd.",
    "pick_range": "Elige un número del 1 al {n}.",

    # -- local library --------------------------------------------------------
    "ask_query": "No he entendido qué poner. ¿Puedes repetirlo?",
    "local_not_found": "No he encontrado {query} en tu música.",
    "playing_local_album": "Pongo el álbum {title} de tu música.",
    "playing_local": "Pongo {title} de tu música.",
    "local_no_artist": "No tengo a {artist} en tu música.",
    "local_no_albums": "No he encontrado álbumes de {artist}.",
    "local_albums": "De {artist} tengo: {listing}. ¿Cuál pongo?",

    # -- kid-safe blocklist ---------------------------------------------------
    "ask_block": "No he entendido qué bloquear. ¿Puedes repetirlo?",
    "already_blocked": "{term} ya está en la lista de temas bloqueados.",
    "blocklist_save_error":
        "No consigo guardar la lista en este momento. "
        "Inténtalo de nuevo en un momento.",
    "block_added": "Vale, he bloqueado {term}.",
    "ask_unblock": "No he entendido qué desbloquear. ¿Puedes repetirlo?",
    "not_in_blocklist": "{term} no está en la lista de temas bloqueados.",
    "blocklist_update_error":
        "No consigo actualizar la lista en este momento. "
        "Inténtalo de nuevo en un momento.",
    "block_removed": "Vale, he desbloqueado {term}.",
    "blocklist_empty": "La lista de temas bloqueados está vacía.",
    "blocklist_listing": "Temas bloqueados: {terms}.",

    # -- web router (localvoice) ---------------------------------------------
    # Source tag appended to a play confirmation: with three sources (local,
    # TIDAL, Qobuz) the reply must say which one answered.
    "from_service": " en {service}",
    "from_local": " de tu música",
    # Room tag appended when a command targets another player («… en la
    # cocina»): {room} is the player's LMS name, spoken as-is.
    "in_room": " en {room}",
    # See the Italian catalog for why an overruled room still gets said.
    "read_as_title": " — lo he leído como un título, así que suena aquí",
    # See the Italian catalog for why this names the room and offers the way
    # out instead of reusing the shared ``pro_required``.
    "room_needs_pro":
        "Hacer eso en {room} necesita Pro. "
        "Dímelo sin la habitación y lo hago aquí.",
    "heard_nothing": "No he oído nada.",
    "router_fallback":
        "No te he entendido. Prueba con: pon, pon el álbum, de mi "
        "música, o qué álbumes tengo de.",
    "internal_error": "Error interno: {error}",
    "pro_required":
        "Esta es una función Pro: se activa desde los ajustes de la "
        "página.",
}
