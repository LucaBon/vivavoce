# Vivavoce — web app vocale locale, in un container.
#
#   docker compose up -d          # vedi docker-compose.yml (consigliato)
#   docker build -t vivavoce .
#   docker run --network host -v vivavoce-data:/data vivavoce
#
# L'immagine contiene la web app locale (localvoice/ + motore engine/).
# Il certificato TLS viene generato al primo avvio nel volume /data.
FROM python:3.12-slim

# Senza TTY lo stdout di Python resta nel buffer: senza questo, `docker logs`
# non mostrerebbe la riga "Pronto: https://..." con l'indirizzo da aprire.
ENV PYTHONUNBUFFERED=1

# cryptography serve solo a generare il certificato self-signed al primo avvio.
RUN pip install --no-cache-dir "cryptography>=42.0"

# Variante ASR (opzionale): --build-arg ASR=1 preinstalla faster-whisper per
# il riconoscimento vocale locale (endpoint /transcribe, funzione Pro).
# Aggiunge ~600 MB all'immagine; il modello Whisper viene scaricato al primo
# uso dentro /data (il volume), quindi sopravvive agli aggiornamenti.
ARG ASR=0
RUN if [ "$ASR" = "1" ]; then pip install --no-cache-dir "faster-whisper>=1.0"; fi

# Variante parola chiave lato server (opzionale, separata da ASR apposta):
# --build-arg WAKEWORD=1 preinstalla openwakeword per l'ascolto continuo
# senza il beep Android (endpoint /wakeword, funzione Pro). Pin ESATTO a
# 0.4.0: le release successive dipendono da tflite-runtime, che non
# pubblica wheel per Python 3.12+ — vedi localvoice/pro/wakeword.py.
ARG WAKEWORD=0
RUN if [ "$WAKEWORD" = "1" ]; then pip install --no-cache-dir "openwakeword==0.4.0"; fi

WORKDIR /app
COPY engine/ engine/
COPY localvoice/ localvoice/
# Solo per la riga di versione (appdata.app_version): la UI la include nel
# testo precompilato di "segnala frase incompresa".
COPY pyproject.toml pyproject.toml
COPY tools/make_cert.py tools/make_cert.py
COPY deploy/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME /data
EXPOSE 8730

# L'app non ha bisogno di root: gira su una porta alta e scrive solo in /data.
# L'entrypoint genera il certificato al primo avvio, quindi /data deve essere
# scrivibile da questo utente — `docker run --user` o un volume con altri
# permessi vanno adeguati di conseguenza.
RUN useradd --system --uid 10001 --home-dir /data vivavoce \
 && mkdir -p /data && chown -R vivavoce:vivavoce /data /app
USER vivavoce

# Un container "su" ma con l'LMS irraggiungibile, o bloccato in attesa, non è
# un container sano: /tls è l'endpoint più economico che esiste qui e non
# tocca l'LMS, quindi risponde esattamente quando il server HTTP serve.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request,ssl; \
port=os.environ.get('VIVAVOCE_PORT','8730'); \
scheme='http' if os.environ.get('VIVAVOCE_HTTPS')=='0' else 'https'; \
ctx=ssl._create_unverified_context(); \
urllib.request.urlopen(f'{scheme}://127.0.0.1:{port}/tls', timeout=4, \
context=ctx if scheme=='https' else None)"

ENTRYPOINT ["/entrypoint.sh"]
