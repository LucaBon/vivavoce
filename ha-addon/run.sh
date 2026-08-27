#!/bin/sh
# Traduce le opzioni dell'add-on nelle variabili VIVAVOCE_* e delega
# all'entrypoint condiviso con l'immagine Docker standalone.
#
# Le opzioni si leggono direttamente da /data/options.json (che il Supervisor
# scrive sempre) con jq, non via bashio: le bashio recenti interrogano l'API
# del Supervisor, che non esiste quando si testa il container fuori da Home
# Assistant. /data è lo storage persistente dell'add-on: certificato TLS,
# licenza Pro e kid-safe sopravvivono a riavvii e update.
set -eu

OPTS=/data/options.json

# `select(. != null)` e non `// empty`: l'operatore alternativo di jq scatta
# anche su `false`, non solo su una chiave assente, quindi `https: false` —
# l'unica opzione booleana che abbiamo — usciva da qui come stringa vuota e
# non veniva mai riconosciuta. L'add-on serviva TLS qualunque cosa avesse
# scelto l'utente, e il reverse proxy davanti parlava HTTP nel vuoto.
opt() {
    if [ -f "$OPTS" ]; then
        jq -r --arg k "$1" '.[$k] | select(. != null)' "$OPTS"
    fi
}

export VIVAVOCE_DATA_DIR=/data

PORT="$(opt port)"
if [ -n "$PORT" ]; then
    export VIVAVOCE_PORT="$PORT"
fi
if [ "$(opt https)" = "false" ]; then
    export VIVAVOCE_HTTPS=0
fi
LMS="$(opt lms_url)"
if [ -n "$LMS" ]; then
    export VIVAVOCE_LMS="$LMS"
fi
PLAYER="$(opt player)"
if [ -n "$PLAYER" ]; then
    export VIVAVOCE_PLAYER="$PLAYER"
fi
CERT_HOSTS="$(opt cert_hosts)"
if [ -n "$CERT_HOSTS" ]; then
    export VIVAVOCE_CERT_HOSTS="$CERT_HOSTS"
fi
MATERIAL="$(opt material_url)"
if [ -n "$MATERIAL" ]; then
    export VIVAVOCE_MATERIAL_URL="$MATERIAL"
fi

exec /app/deploy/docker/entrypoint.sh
