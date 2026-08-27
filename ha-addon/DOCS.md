# Vivavoce — app per Home Assistant

Controllo vocale **in italiano** per un impianto LMS / Squeezebox / Daphile
(TIDAL e Qobuz inclusi): di' «metti Comfortably Numb dei Pink Floyd» e parte *quel*
brano — o ricevi una domanda onesta, mai un brano sbagliato in silenzio.
L'app esegue la web app locale di [Vivavoce](https://github.com/LucaBon/vivavoce):
nessun cloud, nessun account, i comandi restano nella tua rete.

## Installazione

1. **Impostazioni → App → Store → ⋮ → Repository** e aggiungi
   `https://github.com/LucaBon/vivavoce`. (Su Home Assistant precedente a
   2026.2, quando le app si chiamavano *add-on*, la voce di menu è
   **Componenti aggiuntivi**.)
2. Installa **Vivavoce** e avvialo. Di norma non serve configurare nulla:
   LMS viene rilevato automaticamente sulla LAN (UDP) e viene usato il primo
   player trovato.
3. Apri `https://<ip-di-home-assistant>:8730` da telefono/tablet/PC sulla
   stessa rete e accetta **una volta** l'avviso del certificato (necessario:
   il microfono del browser richiede HTTPS). Meglio ancora: dal pannello
   **"📱 Installa come app"** della pagina scarica `/ca.pem` e installala come
   certificato CA — lucchetto verde, niente avvisi, e la pagina si installa
   come **app vera** (PWA) sul telefono.

Poi parla (o scrivi), in italiano: «metti l'album The Wall», «dalla mia musica
metti Aerosmith», «quali album ho di Yes» → «metti la 2», «pausa», «alza il
volume», «cosa sta suonando».

## Opzioni

| Opzione | Significato | Default |
|---|---|---|
| `https` | `false` = solo HTTP (il microfono funziona solo su localhost) | `true` |
| `port` | porta di ascolto | `8730` |
| `lms_url` | URL di LMS, es. `http://192.168.1.50:9000` | auto-discovery |
| `player` | MAC del player da comandare | il primo trovato |
| `cert_hosts` | SAN extra nel certificato (IP/nomi, separati da virgola) | — |
| `material_url` | URL del link "Material Skin" nella pagina | `<lms>/material/` |

Il certificato TLS viene generato al **primo avvio** nello storage persistente
dell'app, quindi l'avviso del browser va accettato una sola volta. Se cambi
`cert_hosts` dopo il primo avvio, riavvia l'app dopo aver cancellato i file
`cert.pem`/`key.pem` dallo storage per rigenerarlo.

## Requisiti

- Un LMS/Daphile sulla stessa rete con almeno un player attivo (per TIDAL:
  plugin TIDAL installato e loggato).
- L'app usa la **rete host** (rende immediata l'auto-discovery UDP e mette
  gli IP giusti nel certificato; senza, la discovery ripiega comunque su una
  scansione unicast della rete).
- Il microfono richiede Chrome/Edge; la casella di testo funziona ovunque.

## Note

- L'app scarica il codice dal **tag** corrispondente alla sua versione
  (`v<versione di config.yaml>`), non da un branch: due build della stessa
  versione, oggi e fra sei mesi, danno lo stesso identico codice. Un update
  dell'app ricompila dal tag nuovo.
- I motori opzionali (riconoscimento vocale locale, parola chiave lato
  server) **non** sono nell'immagine dell'app: pesano centinaia di MB e
  vogliono CPU che un Home Assistant condiviso non ha da regalare. Su HA il
  microfono usa quindi il riconoscimento del browser. Per averli, usa
  l'immagine Docker con `--build-arg ASR=1` / `--build-arg WAKEWORD=1`
  (vedi DEPLOY.md).
- **Cos'è IA qui e cosa no.** IA è la parte che trasforma la voce in testo: su
  Home Assistant è il riconoscimento del browser (quindi Google su
  Chrome/Android, Apple su Safari/iOS — vedi
  [PRIVACY.md](https://github.com/LucaBon/vivavoce/blob/main/PRIVACY.md)).
  Tutto ciò che decide *cosa hai chiesto* non lo è: sono regole scritte a mano,
  nessun LLM, nessun modello che impara da te, nessun profilo di chi parla.
  Poiché riconosce il parlato, Vivavoce è un sistema di IA ai sensi dell'AI Act
  e te lo dice a schermo; la valutazione completa è in
  [docs/ai-act.md](https://github.com/LucaBon/vivavoce/blob/main/docs/ai-act.md).
  Chi la usa in casa non ha obblighi propri.
- Problemi o idee: https://github.com/LucaBon/vivavoce/issues
