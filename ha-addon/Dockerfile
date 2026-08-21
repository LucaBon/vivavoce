# Add-on Home Assistant per Vivavoce (web app vocale locale).
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.21
FROM $BUILD_FROM

# Senza TTY lo stdout di Python resta nel buffer: senza questo, il log
# dell'add-on non mostrerebbe la riga "Pronto: https://..." da aprire.
ENV PYTHONUNBUFFERED=1

# py3-cryptography precompilato (niente toolchain Rust): serve solo a generare
# il certificato TLS self-signed al primo avvio. Il server usa solo stdlib.
# L'entrypoint condiviso invoca "python": su Alpine esiste solo python3.
RUN apk add --no-cache python3 py3-cryptography \
 && ln -sf python3 /usr/bin/python

# L'add-on vive nello stesso repo dell'app, ma il Supervisor builda con questa
# sola cartella come contesto: il sorgente va scaricato dal repo pubblico.
#
# BUILD_VERSION è la versione dell'add-on (config.yaml), passata dal
# Supervisor, e si scarica ESATTAMENTE quel tag: "0.2.0" installa v0.2.0,
# oggi e fra sei mesi. Puntare a main invece legherebbe l'etichetta di
# versione al ramo, non al codice - due installazioni della stessa "0.2.0"
# in giorni diversi otterrebbero sorgenti diversi appena main avanza.
# GitHub toglie la "v" iniziale nella cartella del tarball: v0.2.0 -> 0.2.0.
#
# Se il tag non esiste il build fallisce con un 404 (curl -f): rumoroso al
# momento del rilascio, che è meglio di spedire in silenzio codice non
# rilasciato. Il tag va quindi pushato insieme al bump di versione.
ARG BUILD_VERSION
RUN curl -fsSL "https://github.com/LucaBon/vivavoce/archive/refs/tags/v${BUILD_VERSION}.tar.gz" \
    | tar xz -C /tmp \
 && mkdir -p /app \
 && cp -r "/tmp/vivavoce-${BUILD_VERSION}/engine" \
          "/tmp/vivavoce-${BUILD_VERSION}/localvoice" \
          "/tmp/vivavoce-${BUILD_VERSION}/tools" \
          "/tmp/vivavoce-${BUILD_VERSION}/deploy" /app/ \
 && rm -rf "/tmp/vivavoce-${BUILD_VERSION}"

COPY run.sh /run.sh
RUN chmod +x /run.sh /app/deploy/docker/entrypoint.sh

CMD ["/run.sh"]
