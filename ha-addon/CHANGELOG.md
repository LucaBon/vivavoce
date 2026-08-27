# Changelog

Le modifiche che contano per chi installa **Vivavoce** come app di Home
Assistant. Il changelog completo del progetto — comprese le parti che
riguardano solo Docker o l'esecuzione da sorgente — è
[CHANGELOG.md](https://github.com/LucaBon/vivavoce/blob/main/CHANGELOG.md)
nella radice del repository.

Il formato segue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) e le
versioni [SemVer](https://semver.org/lang/it/). La versione dell'app coincide
sempre con quella del progetto: l'immagine viene compilata dal tag
`v<versione>`, non da un branch.

## [0.4.0] - 2026-08-27

### Aggiunto

- **Vivavoce dice di essere una macchina.** Sotto il microfono c'è ora una
  riga — «Assistente automatico: stai parlando con un software, non con una
  persona» — e, se hai acceso la lettura ad alta voce o l'ascolto continuo,
  una frase detta una volta a inizio sessione. È l'articolo 50(1) del
  Regolamento (UE) 2024/1689 (AI Act), applicabile dal 2 agosto 2026 a
  qualunque sistema che interagisce direttamente con delle persone, e vale
  anche per il software già distribuito. La voce che diventa testo passa
  sempre da un modello neurale — quello del browser, o Whisper sul tuo server
  con l'installazione Pro — quindi l'obbligo è nostro. L'avviso sta accanto ai
  comandi e non nelle impostazioni, e non si può spegnere: un avviso che si
  raggiunge solo da un menu non è un avviso.
  La valutazione completa, articolo per articolo, è in
  [docs/ai-act.md](https://github.com/LucaBon/vivavoce/blob/main/docs/ai-act.md).
  Chi usa Vivavoce in casa non ha obblighi propri.

### Modificato

- **Kid-safe dice perché una canzone è rifiutata, non quanti anni hai.**
  «Questa canzone c'è, ma non è adatta alla tua età» dichiarava di sapere una
  cosa che il filtro non può sapere: qui dentro niente riconosce chi parla. La
  decisione sono tre fatti — kid-safe è acceso, *questo dispositivo* non ha
  digitato il PIN negli ultimi quindici minuti, un termine della lista
  corrisponde — e riguardano un apparecchio e un elenco, non una persona. Ora
  il messaggio dice il motivo vero, che è anche quello su cui puoi agire.

- **Il certificato TLS viene rinnovato a ogni avvio**, non più generato solo
  quando manca. Il certificato del server dura 800 giorni (iOS e macOS
  rifiutano di più), il che trasformava «genera se assente» in una scadenza
  senza nessuno che la rinnovasse. Vengono riemessi solo i certificati firmati
  dalla nostra CA, e la CA viene riusata: **non devi reinstallare niente sui
  telefoni**. In cambio l'app scrive nella sua cartella dati a ogni avvio.

- **Il controllo dell'host vale ora anche in lettura.** Prima lo faceva solo
  la scrittura, quindi la protezione contro il DNS rebinding non copriva
  nessuna pagina leggibile. **Se raggiungi Vivavoce con un nome DNS tuo,
  mettilo in `VIVAVOCE_ALLOWED_HOSTS`**: una configurazione così ora riceve un
  403 sulla pagina stessa, mentre prima la pagina si apriva e fallivano solo i
  comandi. Non smette di funzionare nulla che funzionasse — la scrittura ha
  sempre richiesto la stessa lista — ma il guasto è più rumoroso.

### Corretto

- **`https: false` viene finalmente rispettato.** L'app legge le sue opzioni
  con `jq -r '.[$k] // empty'`, e `//` scarta `false` esattamente come una
  chiave assente: `https` è l'unica opzione booleana che esponiamo, quindi era
  l'unica a farne le spese.

- **Il blocco a cinque tentativi del PIN ne permetteva molti di più.** La
  verifica leggeva il contatore, passava ~100 ms in PBKDF2 e solo dopo lo
  incrementava, senza niente che tenesse insieme le due cose: ogni richiesta
  arrivata prima della prima scrittura vedeva zero tentativi.

- **`kidsafe.json` aveva due scrittori e nessun lucchetto in comune**: la parte
  PIN e la parte lista leggevano e riscrivevano tutto il file, e chi leggeva
  per primo scriveva per ultimo, perdendo in silenzio le modifiche dell'altro.
  Un salvataggio che fallisce ora lo dice, invece di sparire.

- **«metti X in cucina» non sposta più la musica di tutti gli altri.**

- **Spegnere l'ascolto continuo chiude anche la registrazione che aveva
  aperto.** Prima quella arrivava fino al suo limite di trenta secondi,
  trascriveva e — con l'invio automatico, che l'ascolto continuo implica —
  rispondeva a quel che si stava dicendo in stanza, molto dopo che il pannello
  si era spento dicendo «tocca il microfono».

- **A trial scaduto sparisce tutto il blocco dell'ascolto continuo**, non solo
  il paragrafo di spiegazione: scelta del motore, campo della parola chiave e
  suggerimenti restavano a schermo sotto una casella appena disattivata.

- **La parola chiave sceglie la frase che la contiene**, non una qualsiasi più
  lunga del frammento spurio che il riconoscitore aveva lasciato in mano.

- **Una parola chiave lato server che non trova il suo modello non si dichiara
  più attiva** e poi non riconosce niente.

- **Un'installazione scaduta non si sente più dire a ogni avvio che ha quattordici
  giorni di prova freschi.**

- **Il service worker non conserva più una pagina di errore come se fosse
  l'app**: un 403, un 404 o un 500 potevano prendere il posto di quel che
  l'installazione aveva messo da parte.

- **La barra di avanzamento sopravvive a perdere il brano sotto il dito**: il
  controllo ogni cinque secondi, un cambio di scheda o una richiesta fallita
  potevano azzerarne lo stato a trascinamento iniziato.

- **Un decennio non viene più letto con la voce sbagliata**: l'anno finiva fra
  i nomi stranieri della frase, e in «1985» non c'è niente su cui indovinare
  una lingua, così «Ho messo qualcosa del 1985» si spezzava a metà in inglese.

## [0.3.0] - 2026-08-26

### Aggiunto

- **14 giorni di Pro completo alla prima installazione**, microfono incluso:
  nessuna chiave, nessun account, nessuna chiamata di rete. La finestra è un
  timestamp nello storage persistente dell'app, aperto al primo avvio, quindi
  svuotare i dati del browser non la fa ripartire. Alla scadenza i comandi
  scritti continuano a funzionare come prima: non si rompe e non si cancella
  niente.
- **Richieste vaghe che suonano qualcosa, e lo dicono.** «metti qualcosa di
  rilassante», «musica per cena», «metti un po' di jazz», «musica anni
  ottanta», la musica di Natale, quella strumentale. Parte dai generi della
  tua libreria e ripiega sulle playlist del servizio di streaming solo se in
  casa non c'è niente. Ogni risposta rilegge cosa ha messo, e «un'altra»
  cambia. Le richieste che *nominano* un brano, un album o un artista non
  cambiano di una virgola: lì non si indovina.
- **Gestione della coda**: «aggiungi X alla coda», «metti X dopo questa»,
  «svuota la coda», «cosa c'è in coda».
- **Preferiti e radio**: «riproduci i preferiti», «metti la radio X». Usa i
  preferiti di LMS, non un plugin radio specifico, quindi funziona con le
  stazioni che hai già salvato comunque le hai salvate.
- **Setup guidato del certificato**, che su Home Assistant è il punto in cui
  si perde più gente: la pagina si apre su `https://<ip>:8730` e il browser ci
  mette davanti «la connessione non è privata». Il pannello *"Installa come
  app"* ora riconosce quella situazione, si apre da solo, mostra i due
  passaggi per **il tuo** dispositivo e verifica che abbiano funzionato — la
  verifica non è una supposizione: un browser rifiuta di registrare un service
  worker su un certificato non fidato, quindi una registrazione riuscita *è*
  la prova che la CA è installata.
- **`POST /api/v1/command`, un'API documentata** ([docs/api.md](https://github.com/LucaBon/vivavoce/blob/main/docs/api.md)):
  un'automazione, uno script o un blueprint di Home Assistant può mandare una
  frase e ricevere una risposta strutturata — `needs_choice` dice che Vivavoce
  ha fatto una domanda invece di suonare, `conversation_id` nomina la sessione
  a cui appartiene una lista numerata — senza leggere il sorgente per capire
  cosa significano i campi. Il vecchio `POST /command` continua a funzionare.
- **Segnalazione di una frase non capita**: il pulsante salva il report sul
  tuo dispositivo e apre una issue GitHub precompilata da rivedere prima di
  inviarla. L'app non manda niente da sola.

### Corretto

- **Un apostrofo non nasconde più un nome bloccato al filtro bambini.** Prima
  di controllare la lista, il testo viene normalizzato e gli apostrofi vengono
  tolti — di proposito, perché il riconoscitore scrive «dont stop me now» e il
  titolo è *Don't Stop Me Now*. Togliendoli, però, le parole vicine si saldano
  e il termine bloccato non ha più un confine su cui corrispondere: una lista
  con *Eminem* non vedeva più "Eminem's Greatest Hits", una con *Estasi* non
  vedeva più "L'Estasi dell'Oro". Con l'elisione — l', dell', un', sull' — in
  italiano bastava un articolo per rendere irraggiungibile un nome bloccato, e
  gli album erano il caso peggiore, perché il titolo è l'unico campo in cui un
  risultato in streaming porta un nome. Ora vengono controllate entrambe le
  grafie, e un «ass» bloccato continua a non corrispondere a «bassista».

- **Le canzoni con «di», «della» o «by» nel titolo si riproducono di nuovo.**
  L'ultimo connettore di una richiesta viene letto come confine fra titolo e
  artista, ed è quello che fa trovare «Stand By Me by Ben E. King» — ma
  inventava un artista per ogni titolo che ne contenesse uno: «Cuore di Vetro»
  diventava *Cuore* di *Vetro*, «Notte Prima degli Esami» diventava *Notte
  Prima* di *Esami*. Da quando l'app dice che l'artista chiesto non è fra i
  risultati, le due cose insieme trasformavano «metti Cuore di Vetro» in «Non
  ho trovato Cuore di Vetro», con il brano giusto in cima all'elenco. Una
  richiesta che corrisponde per intero a un titolo, connettore compreso, ora
  viene presa per il titolo che è. Anche i titoli che *iniziano* con un
  connettore perdevano la prima parola — «By the Way» cercava "the Way" — e non
  succede più.

- `/command`, `/kidsafe`, `/player` e `/license` non chiudono più la
  connessione quando ricevono un corpo JSON che non è un oggetto (`null`, un
  numero, una stringa, una lista).

- **Un rifiuto non fa più partire la musica nella stanza sbagliata.** L'app
  prova più trascrizioni del riconoscitore, fermandosi alla prima che funziona,
  e un rifiuto sembrava qualcosa da riprovare. Così «metti Beatles in salotto»
  senza Pro veniva rifiutato, e poi la seconda trascrizione — «metti Beatles»,
  senza il nome della stanza — passava accanto al rifiuto appena dato e faceva
  partire la musica dove puntava il selettore, senza dire perché. Kid-safe
  aveva lo stesso buco: un cantante bloccato poteva essere richiesto finché una
  grafia non passava. I rifiuti che riguardano *chi sta chiedendo* — niente
  Pro, non sei il genitore, non adatto a chi ascolta — ora chiudono il turno;
  quelli che riguardano le *parole* si riprovano come prima.

- **Le risposte sulla lista dei brani bloccati non nominano più una stanza.**
  «blocca Eminem in salotto» rispondeva «Ok, ho bloccato Eminem in Salotto»,
  che descrive una lista per stanza che non esiste: la lista vale per tutta la
  casa.

- `ok`, nella risposta di `POST /api/v1/command`, dice davvero se il comando è
  stato eseguito: alcuni rifiuti venivano marcati come riusciti.

## [0.2.0] - 2026-08-21

### Modificato

- **SqueezeSay si chiama Vivavoce e lo slug è cambiato** (`squeezesay` →
  `vivavoce`): per il Supervisor questa è un'app **nuova**. Chi aveva la
  vecchia deve disinstallarla, aggiungere di nuovo il repository
  (`https://github.com/LucaBon/vivavoce`) e installare **Vivavoce**. Il
  vecchio `/data` non viene migrato: l'avviso del certificato va accettato
  un'altra volta e la chiave di licenza va reinserita (consuma una delle 5
  attivazioni).
- Le variabili d'ambiente sono `VIVAVOCE_*`. I vecchi nomi `SQUEEZESAY_*`
  funzionano **solo per questa versione**, stampando un avviso.

### Aggiunto

- **Inglese come seconda lingua**, e il supporto a **Qobuz** accanto a TIDAL.
- **Pannello "sta suonando"**: copertina, titolo/artista/album, spia
  play/pausa, trasporto, barra di avanzamento trascinabile e cursore del
  volume.
- **Multi-room** (Pro): un comando può scegliere la stanza al volo — «metti
  Time **in cucina**», «pausa in salotto» — e il «metti la 2» che segue resta
  in quella stanza.
- **Timer di spegnimento**: «spegni tra 30 minuti», «annulla il timer».
- **Kid-safe** (Pro): blocklist protetta da PIN, applicata lato server per
  ogni dispositivo della rete, modificabile a voce o dalle impostazioni.
- **Spia di stato di LMS**: il LED in testata diventa rosso, con un messaggio
  leggibile, quando il music server non risponde.
- **Vivavoce Pro**: licenza una tantum che sblocca microfono, parola chiave,
  voci di read-back e kid-safe. Attivazione una volta sola online, poi in
  cache: offline non disattiva niente. Il core — comandi scritti, ricerca,
  riproduzione, trasporto — resta gratuito ed è AGPL-3.0.
- **Riconoscimento vocale locale** (Pro): trasformare la voce in testo sul
  tuo server invece che nel cloud del browser. **Non è nell'immagine di questa
  app** — pesa centinaia di MB e vuole CPU che un Home Assistant condiviso non
  ha da regalare — quindi qui il microfono usa il riconoscimento del browser.
  Per averlo, l'immagine Docker con `--build-arg ASR=1`.

## [0.1.0] - 2026-07-14

- Prima versione dell'app, pubblicata con lo slug `squeezesay`: la web app
  vocale in italiano per LMS/Squeezebox/Daphile installabile in un click su
  Home Assistant OS/Supervised, con auto-discovery di LMS e certificato TLS
  generato al primo avvio nello storage persistente.
