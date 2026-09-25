# Changelog

## Unreleased

### New

- **Il punto d'ascolto torna su Audiobookshelf.** Mentre un audiolibro messo
  da Vivavoce suona, ogni mezzo minuto la posizione viene salvata su
  Audiobookshelf, la stessa che usa la sua app. Se in mezzo al libro metti
  un disco — a voce, da Material Skin o dal telecomando — «riprendi il libro
  X» riparte da dove eri, perdendo al più l'ultimo mezzo minuto; e da lì
  riparte anche l'app sul telefono. Vale anche il contrario: se riprendi il
  libro sull'impianto, è l'impianto a scrivere, e la posizione che il
  telefono aveva raggiunto nel frattempo viene sostituita. Un impianto in
  pausa non scrive niente. Il libro non viene mai segnato come finito:
  quello resta all'app. Con l'impianto spento il salvataggio aspetta in
  silenzio, e non rallenta il primo comando quando lo riaccendi. Senza
  `--library` non parte niente.

- **Una ripresa che non riesce lo dice.** Se il punto salvato non si può
  raggiungere — il lettore non salta davvero, o Audiobookshelf non conosce
  la durata dei file — la risposta è «Non riesco a riprendere X da 2 ore:
  questo impianto lo fa ripartire dall'inizio», invece di un «Metto
  l'audiolibro» che nascondeva la posizione persa. Provato sull'impianto
  vero: LMS 9 accetta il salto dentro un `.m4b` servito da Audiobookshelf,
  dice di saperlo fare, e riparte da zero senza errori. Vivavoce ora
  controlla dove il lettore è arrivato davvero; e se non è arrivato, non
  salva niente, così la posizione di Audiobookshelf non viene sovrascritta
  con quella sbagliata. Su LMS un audiolibro in un file unico si ascolta
  quindi dall'inizio, senza capitoli né ripresa; uno a più file funziona in
  tutto.

### Changed

- **Un audiolibro si attraversa per capitoli.** «capitolo successivo»,
  «capitolo precedente» e «a che capitolo sono», nelle cinque lingue, su un
  libro messo da Vivavoce. I capitoli sono quelli di Audiobookshelf, anche
  dentro un unico file `.m4b`; un libro che non ne ha conta un capitolo per
  file. La risposta dice il numero, e il titolo quando è più del numero
  («capitolo 3 di 19, "Un incontro inatteso"»). Se sullo stesso lettore nel
  frattempo è partito altro — un disco messo da Material Skin, per esempio —
  la risposta dice che non sta suonando un audiolibro, e non tocca niente. Un
  lettore che non sa saltare dentro un file non riceve un capitolo che
  inizia a metà di uno: lo dice invece di mettere quello prima. «avanti» e
  «indietro» da soli continuano a passare al file successivo e precedente.

- **Un audiolibro già iniziato riparte da dove era rimasto.** «metti
  l'audiolibro X», e ora anche «riprendi il libro X», leggono il punto
  d'ascolto che Audiobookshelf tiene già per la sua app, e ripartono da lì:
  mettono in coda solo i file da quel punto in avanti e saltano al secondo
  giusto; la risposta dice da dove, in ore e minuti («da un'ora e 30
  minuti»). Se il lettore non sa saltare dentro un file, o Audiobookshelf non
  conosce la durata dei file, la risposta dice il punto da cui l'ascolto
  riparte davvero, non quello salvato. Un libro finito o mai aperto
  parte dall'inizio, come prima. «metti a velocità 1.2» ha una risposta che si può usare
  invece di un errore, e non tocca il lettore. E se a non rispondere è
  Audiobookshelf, la risposta dice Audiobookshelf invece di «l'impianto».

- **La pagina si legge meglio, su più schermi e anche senza mouse.** Una
  revisione dell'interfaccia contro le euristiche di Nielsen e WCAG AA. Il
  suggerimento nella casella e il bordo dei campi arrivano al contrasto
  minimo, e su iPhone i campi delle impostazioni non fanno più zoomare la
  pagina. Con il telefono in orizzontale la conversazione ha di nuovo
  spazio: da 30 a oltre 200 px. La libreria di Material Skin è un pulsante
  sopra le impostazioni invece di un link grigio in fondo, e il suo pannello
  si chiude con Esc e restituisce il fuoco. Le impostazioni sono divise in
  Ascolto, Musica, Risposta e Pro, e nessun menu vi è più tagliato a metà.
  Sotto un microfono bloccato la riga di stato dice di scrivere invece di
  invitare a toccarlo. Il microfono e il pulsante play/pausa hanno un nome
  che dice cosa fanno.

- **La demo mette Vivavoce accanto a un assistente qualunque.** Ogni frase
  che chiede musica ora mostra due colonne: che cosa avrebbe messo un
  assistente che fa della frase parole chiave e suona il primo risultato, e
  che cosa ha fatto Vivavoce. «metti Time di Hans Zimmer» lì diventa il
  «Time» dei Pink Floyd, e «Wish You Were Here» diventa «Here Comes the Sun»,
  segnati in rosso; dove i due fanno la stessa cosa la pagina lo dice. La
  regola dell'altro assistente è scritta in pagina ed è onesta di proposito
  (stesse frasi, stesso scaffale, parole corte ignorate: niente pagliaccio),
  e quando Vivavoce non trova qualcosa che il primo risultato indovina —
  «Bohemian Rapsody» — la pagina lo ammette invece di contarlo.
  In cima c'è il conto dei brani sbagliati evitati, la risposta si sente
  (la voce del browser, disattivabile con 🔊), e l'impianto finto ha una
  copertina disegnata, la barra di avanzamento e la coda; i comandi mandati
  all'impianto sono ancora lì, dentro un riquadro chiuso.

### Internal

- **La CI non fallisce più per aver trovato quello che cercava.** Il
  controllo d'avvio dell'add-on faceva `docker logs addon | grep -q
  "Pronto"`: sotto `pipefail`, quando `grep` trova la riga ed esce mentre
  `docker` sta ancora scrivendo, la pipe finisce con 141 e il passo diventa
  rosso. È successo sul push della 0.8.0. Ora il log si legge prima e si
  cerca dopo, e la scelta del tag più recente usa `git for-each-ref
  --count=1` invece di `| head -1`, che è la stessa gara. Un test in
  `tests/test_packaging.py` rifiuta d'ora in poi ogni `| grep -q`, `| grep
  -m` o `| head` nei passi dei workflow.

## 0.8.0 — September 2026

### New

- **Una demo nel browser, senza installare niente.** Sul sito c'è una
  pagina nuova, [`demo/`](https://lucabon.github.io/vivavoce/demo/), dove si
  scrive o si dice una frase — «metti Time dei Pink Floyd», «vai avanti di 30
  secondi», «quali sono i brani di Pink Floyd» e poi «metti la 2» — e si vede
  che cosa risponde Vivavoce e che cosa manderebbe all'impianto. Il motore è
  quello vero: lo stesso Python dell'app, caricato nella scheda con Pyodide
  (circa 5 MB la prima volta, 2–4 secondi). L'impianto invece è finto, con sei
  brani e nessun suono, scelti apposta per mettere alla prova la promessa:
  due brani si chiamano «Time», «Money» c'è solo dei Pink Floyd, «Wish You
  Were Here» non c'è. Chiedi la cosa giusta e parte quella; chiedi quella che
  non c'è e te lo dice, senza far partire altro. Cinque lingue, microfono
  dove il browser lo offre.

  L'app installata non cambia di una riga: la pagina scarica i file del
  motore da jsDelivr, alla stessa versione che il sito pubblica.

- **Gli audiolibri si chiedono a voce.** Con `--library audiobookshelf`
  collegato, «metti l'audiolibro Lo Hobbit» — o «leggimi il libro …», "play
  the audiobook …", «spiel das Hörbuch …», «mets le livre audio …», «pon el
  audiolibro …» — cerca il libro su Audiobookshelf e ne mette in coda i
  capitoli, in ordine, sull'impianto che già suona. Se il primo risultato
  somiglia poco a quello che hai detto, prima chiede «Intendi l'audiolibro
  …?»: un libro dura ore, e partire col libro sbagliato in silenzio è
  proprio l'errore che l'app promette di non fare. Un libro bloccato dal
  kid-safe non viene trovato né nominato.

  La parola che conta è «audiolibro» (o «leggimi il libro»): «metti il libro
  della giungla» resta una canzone e lo scaffale non viene interrogato.
  Senza `--library` non cambia niente, nemmeno per queste frasi.

- **«Vai avanti di 30 secondi», «torna indietro di un minuto».** Il salto
  dentro il brano, nelle cinque lingue: secondi o minuti, a cifre o a parole,
  «mezzo minuto» compreso. Finora «avanti» e «indietro» volevano dire solo
  brano successivo e precedente — e lo vogliono dire ancora quando nella
  frase non c'è un'unità di tempo. Il salto si ferma all'inizio del brano e
  un secondo prima della fine, invece di scivolare nel capitolo dopo. Un
  impianto che non sa spostarsi lo dice.

  Non ancora: capitoli, velocità di lettura e «riprendi il libro da dove ero
  rimasto». Arrivano nei prossimi passi.

## 0.7.0 — September 2026

### New

- **Audiobookshelf si collega accanto all'impianto — ancora senza frasi.**
  Tre opzioni nuove, `--library audiobookshelf`, `--library-url` e
  `--library-token` (con i gemelli `VIVAVOCE_LIBRARY*` e le tre voci
  nell'app Home Assistant), collegano un catalogo di audiolibri che si
  ascolta **attraverso** LMS o Music Assistant: i libri da lì, gli
  altoparlanti da qui. All'avvio l'app dice quante librerie di libri vede, o
  perché non le vede.

  Per ora è solo il collegamento: nessuna frase raggiunge ancora un libro, e
  quelle arrivano nei prossimi passi. Senza `--library` non cambia niente —
  non si costruisce, non si interroga e non si stampa nulla.

  Due cose da sapere già adesso. I file li scarica l'impianto, non questo PC,
  quindi l'indirizzo dev'essere l'IP di rete e non `localhost` (l'app avvisa).
  E la chiave API finisce negli indirizzi in coda sull'impianto, perché un
  hi-fi non sa mandare un'intestazione: va creata per un utente di
  Audiobookshelf che può solo ascoltare. Un Audiobookshelf spento all'avvio
  non ferma l'app: la musica non c'entra.


- **Vivavoce può sapere da che stanza gli hai parlato.** Finora la stanza
  esisteva in un modo solo: dirla. «metti Time in cucina» funziona dal
  2026-08-26 ed era la risposta giusta a metà, perché nella stanza in cui sei
  già non hai voglia di nominarla — e un satellite vocale in cucina sa
  benissimo dov'è, semplicemente non aveva modo di dirlo. Ora ce l'ha: il
  contratto `POST /api/v1/command` accetta un campo `room`, e il blueprint di
  Home Assistant può riempirlo con l'**area** del dispositivo che ha sentito
  la frase.

  Sono due cose diverse e la precedenza lo dice: un `player` esplicito (che è
  un id, non un nome) batte tutto; una stanza **detta nella frase** batte
  quella d'origine, perché chiedere il salotto stando in cucina è
  un'intenzione e non un errore; l'origine vale quando non c'è nient'altro. La
  risoluzione nome→lettore non è nuova: è la stessa di `pro/multiroom.py` che
  la frase parlata usa da sempre, così la soglia è una e la regola sui lettori
  scollegati è una.

  **Se il nome non corrisponde a nessun lettore collegato, Vivavoce lo dice e
  non fa niente.** Non ripiega sul lettore di default, ed è la parte da capire
  prima di accendere l'opzione: far partire la musica in salotto perché la
  cucina non si è risolta è un fatto fisico in casa di qualcuno, che qualcuno
  deve alzarsi e disfare — mentre un rifiuto costa una ripetizione. È la
  stessa asimmetria già scelta per la stanza detta a voce. Il rovescio onesto
  della medaglia: un'area scritta male fallisce *ogni* comando da quel
  satellite finché non la si sistema, ed è esattamente per questo che nel
  blueprint l'opzione **«Play in the room that was spoken to» è spenta di
  default** — si accende quando i nomi delle aree e quelli dei lettori
  combaciano.

  Il campo richiede Pro (multi-room). Senza, viene **ignorato e non
  rifiutato**: chi lo manda non ha chiesto Pro, ha detto dov'era, e
  un'installazione free ha un lettore solo. Il contratto v1 permette di
  aggiungere campi e non di toglierne: `docs/api.md` ora porta sia il campo
  sia la sezione che spiegava perché in v1 non c'era — due dei suoi tre
  argomenti reggono ancora, e il terzo (progettare senza un client vero) è
  scaduto il giorno in cui il blueprint è stato provato su un Home Assistant
  vero.

### Fixed

- **Un Audiobookshelf che risponde a sproposito non impedisce più l'avvio.**
  Il client trasformava in errore di dominio un corpo che non è JSON, e
  lasciava passare un corpo che **è** JSON valido ma non è l'oggetto che l'API
  documenta: la pagina di errore di un reverse proxy, un captive portal, uno
  schema che si è mosso. Tre frame più su diventava
  `AttributeError: 'list' object has no attribute 'get'` — che non è un
  `PlayerError`, quindi nessuno lo prendeva, e usciva da `server.main()`:
  l'assistente vocale si rifiutava di partire per colpa di uno scaffale di
  libri. La musica non c'entra niente con i libri, ed è la promessa che questo
  modulo fa dal primo giorno.

  Ora il controllo di forma sta al confine del client, dov'è già la regola
  «ogni guasto è un errore di Audiobookshelf», e vale riga per riga e non solo
  sulla busta: una libreria scritta male non si porta via quelle accanto. Una
  durata scritta a parole vale zero invece di far sparire il libro.

- **Un elenco aperto non si mangia più la richiesta dopo.** «Quali brani dei
  Pink Floyd», poi «metti Money for Nothing dei Dire Straits»: partiva
  «Money», quello dell'elenco. La scelta per nome accettava un titolo che
  *comparisse* dentro la frase, e l'elenco resta scegliibile per cinque
  minuti — quindi per cinque minuti ogni richiesta che conteneva una di quelle
  parole veniva risposta dall'elenco, in silenzio e con la canzone sbagliata.
  Lo stesso succedeva con «Time After Time» su un «Time» in elenco.

  Adesso conta quello che **resta** tolto il titolo: se sono solo articoli e
  parole di riempimento («metti l'album Fragile», «Money per favore») la
  scelta vale; se resta del contenuto — un nome di band, il resto di un
  titolo — non era una scelta, e la frase va alla ricerca come sarebbe andata
  prima che l'elenco si aprisse. Le parole di riempimento sono per lingua,
  accanto agli altri connettori (`engine/connectors/`).

- **«Tra un'ora e mezza» sono novanta minuti, non sessanta.** Le durate
  venivano lette solo dall'inizio: «un'ora e mezza» agganciava «un'ora» e il
  timer partiva mezz'ora corto — senza dirlo, e alla fine non c'è nessuno
  sveglio a sentire la differenza. Ora la coda dev'essere **tutta** una
  durata, e le forme che servono ci sono in tutte e cinque le lingue: «un'ora
  e mezza», «due ore e mezza», «un'ora e venti minuti», "an hour and a half",
  «anderthalb/eineinhalb Stunden», «une heure et demie», «dos horas y media».

  Il tedesco era il caso peggiore: «in anderthalb Stunden» non era una durata
  per nessun motivo leggibile, e la frase ricadeva sul passo della pausa —
  che metteva in pausa **subito**, cioè la risposta più rumorosa possibile a
  «lasciala suonare ancora un'ora e mezza». Adesso una durata letta **a
  metà** non diventa più una pausa.

  A metà, non «illeggibile», e la differenza è tutto il punto: in quattro
  lingue su cinque la preposizione che introduce il ritardo è la stessa che
  introduce una **stanza** — «pause in the kitchen», «stopp in der Küche»,
  «arrête dans la cuisine» — e la stanza viene tolta prima solo se il
  multi-stanza è installato **e** il nome corrisponde a un lettore vero. Su
  una build free, o con una stanza che non esiste, rifiutare qualunque coda
  illeggibile avrebbe lasciato il comando più ordinario dell'app senza fare
  niente. Quindi: una cucina mette in pausa, «due ore e un quarto» no.

- **Gli ordinali con l'accento, detti da soli, sono di nuovo una scelta.**
  «Troisième», «fünfte», «séptima»: con un elenco aperto il passo che legge
  una parola sola accettava solo `a-z0-9`, quindi la parola veniva rifiutata
  prima ancora di chiedere alla tabella che conosceva la risposta, e il turno
  moriva come «non ho capito».

- **I sosia di «tidal» che sono parole vere valgono solo a fine frase.** I
  riconoscitori scrivono «Titel», «titles» e «Vidal» per TIDAL, e davanti alla
  richiesta quelle parole si mangiavano l'inizio del titolo: «play from titles
  of the unknown» cercava «of the unknown» su TIDAL, e quello che era stato
  chiesto non veniva cercato mai. Alla fine della frase («metti X da Titel»)
  non c'è altro che possano essere, e lì continuano a valere. Aggiunto anche
  un confine di parola davanti alla preposizione, che senza di esso veniva
  trovata **dentro** la parola prima («Anaconda titles»).

- **«Apri le impostazioni di LMS» solo se l'impianto è un LMS.** Le due frasi
  che mandano a riconnettere un plugin nominavano LMS in tutte e cinque le
  lingue, anche su Music Assistant: una pagina di impostazioni che lì non
  esiste. Ora il nome dell'impianto lo dice l'impianto, come già fa per i
  servizi.

- **`--services` è validato anche quando la risposta è «nessuno».** «Non sono
  riuscito a chiedere» e «ho chiesto, e non ne ha» finivano nello stesso ramo,
  così su un Music Assistant senza provider configurati un `--services tidal`
  passava senza controllo: il selettore offriva TIDAL e ogni richiesta
  rispondeva «TIDAL non è collegato» — la stessa lista inventata che il ramo
  `auto` qui sotto ha smesso di stampare. Un impianto che non ha proprio il
  concetto di servizi continua a prendere la lista com'è scritta: è il varco
  d'emergenza, e un varco che ha bisogno della rilevazione non è un varco.

- **Nessun servizio rilevato non vuol dire TIDAL.** Con `--services auto` e
  una rilevazione vuota l'app assumeva `["tidal"]` e lo stampava come un
  fatto: il selettore della sorgente offriva un plugin che quella casa non ha
  mai avuto, e ogni richiesta finiva su «TIDAL non è collegato». Ora lo dice
  com'è — restano la libreria locale e i comandi di riproduzione — e non
  inventa niente.

- **Un titolo col punto dentro non viene più spezzato in due.** «Riproduco
  Mr. Brightside» diventava «Riproduco Mr da TIDAL. Brightside.», e lo stesso
  per ogni «Pt. 2» e «Vol. 1» in libreria: l'etichetta della sorgente veniva
  infilata al primo punto della frase. Ora il posto dell'etichetta lo dice il
  messaggio, non un punto trovato nel testo.

- **Una lettura fallita non cancella più il PIN.** Il file del kid-safe viene
  letto intero, cambiato di una chiave e riscritto intero. La lettura
  ripiegava su «vuoto» per *qualunque* errore — un file troncato da una
  mancanza di corrente, un permesso cambiato sotto l'app — e la scrittura
  subito dopo rendeva vero quel vuoto: PIN e contatore dei tentativi spariti,
  in silenzio. Ora solo «il file non c'è ancora» è un vuoto; tutto il resto
  fallisce il salvataggio e lascia il file com'era.

- **Un campo dell'API con il tipo sbagliato riceve una risposta.** `text` era
  già protetto; `lang` e `conversation_id` no, ed erano i due peggiori: un
  `lang` che arrivava come lista faceva cadere la connessione **senza
  risposta**, e un `conversation_id` come lista tornava come «errore interno».
  Un tipo sbagliato adesso vale come «campo non inviato» — la richiesta viene
  risposta, nella lingua predefinita.

- **Gli errori dei motori audio restano sul server.** `/transcribe` e
  `/wakeword/*` rimandavano al client il testo dell'eccezione, che contiene i
  percorsi delle cartelle dei modelli e dei dati — e questi endpoint
  rispondono a chiunque sulla LAN. Ora il dettaglio va nel log del server, dove
  lo legge chi può farci qualcosa, e la risposta porta una parola sola. Anche
  l'errore interno di `/api/v1/command` finisce finalmente nel log: prima non
  ce n'era traccia da nessuna parte.

- **Il modello della parola chiave viene verificato prima di essere usato.**
  Di un download da ~50 MB si controllava solo che lo zip si aprisse e
  contenesse una cartella col nome giusto: qualunque archivio che rispondesse
  sì diventava il modello con cui la casa ascolta. Ora di ogni modello sono
  fissate dimensione e impronta SHA-256 (calcolate una volta e verificate
  contro l'MD5 e la dimensione che upstream pubblica), il download si ferma
  se supera il previsto invece di riempire il disco, e un archivio che
  dichiara di scompattarsi in più di 1 GB viene rifiutato prima di scrivere
  un byte. Anche il modello di riconoscimento vocale è fissato a una
  revisione precisa invece di «quello che c'è oggi».

- **I token non passano più dalla riga di comando** del processo, che è
  leggibile da chiunque possa fare `ps` e finisce nei dump di debug. Arrivano
  dall'ambiente, dove già stavano.

- **L'unità systemd gira con un utente suo e il disco in sola lettura.**
  `NoNewPrivileges`, `ProtectSystem=strict` e un elenco esplicito di ciò che
  il servizio può scrivere. **Chi installa o reinstalla l'unità deve creare
  l'utente prima** — i due comandi sono in DEPLOY.md; un'installazione già in
  funzione continua a girare con la sua unità attuale finché non la sostituisce.

- **La catena di costruzione è fissata.** L'immagine Docker parte da un digest
  e non da un'etichetta che si muove, installa versioni esatte invece di
  «l'ultima di oggi», e le action della CI sono fissate al commit con il tag
  nel commento accanto. Nessun job ha più il permesso di scrivere nel
  repository, tranne quello che pubblica l'immagine.

- **Una porta esposta su internet non consegna più l'impianto a chi la
  trova.** L'app non ha account né password, per progetto: è sulla rete di
  casa e risponde a chi chiede. Ma tutte le difese che aveva guardavano *da
  quale pagina* arrivava la richiesta, e nessuna sa distinguere il telefono
  sul divano da uno scanner che ha trovato una porta aperta sul router — con
  un port forward il `Host` è quello che manda il router, e un client che non
  è un browser non manda né `Origin` né `Sec-Fetch-Site`. Ora una connessione
  che non arriva da un indirizzo di casa viene rifiutata prima di essere
  servita: niente musica, niente PIN di kid-safe, e niente pannello di
  Material — da cui si installano i plugin dell'LMS. Contano come casa gli
  indirizzi privati, loopback, link-local e `100.64/10`, che è quello che usa
  Tailscale: raggiungere il proprio impianto da fuori con una VPN continua a
  funzionare senza configurare niente. Chi espone la porta di proposito lo
  dice con `--allow-public-peers`, e allora ha `--api-token` da mettere
  davanti a `/api/v1` e al proxy. DEPLOY.md spiega perché usarli insieme.

- **Le sessioni della parola chiave lato server hanno un tetto.** La pulizia
  delle sessioni inattive era un orologio, non un limite: entro i due minuti
  di attesa, un chiamante che invent(av)a un identificativo per richiesta
  otteneva un riconoscitore per richiesta, e l'identificativo arriva dalla
  richiesta stessa. Ora sono al massimo 32 e la più vecchia lascia il posto.

- **La CA locale non può più firmare per qualunque sito.** Installare
  `ca.pem` su un telefono significa che quel telefono crede a chi possiede
  `ca-key.pem` — e quella chiave sta accanto a `ca.pem`, cioè dentro `/data`,
  cioè in ogni backup. Finora poteva firmare un certificato per *qualsiasi*
  dominio, quindi una copia della chiave bastava a mettersi in mezzo fra i
  dispositivi di casa e il resto del web. Ora il certificato dichiara dove si
  ferma: solo indirizzi privati e nomi locali (`.local`, `.lan`,
  `.home.arpa`…), e vale dieci anni invece che fino al 2044. Una CA creata
  dalle versioni precedenti viene segnalata a ogni avvio e **non** sostituita
  da sola — l'impronta è quella che ogni telefono ha installato; in DEPLOY.md
  ci sono i tre comandi per cambiarla quando fa comodo, e fino ad allora
  tutto continua a funzionare come prima.

- **Un indirizzo scritto nella pagina di configurazione non presta più
  l'indirizzo dell'app.** Quella casella non risponde solo a chi guarda la
  pagina: risponde a qualunque dispositivo della rete di casa. Finché
  l'impianto non risponde, un indirizzo mandato lì veniva adottato — e
  diventava anche il bersaglio del proxy che apre il pannello di Material
  dentro la pagina, cioè quell'indirizzo poteva servire pagine e codice
  *sotto l'indirizzo dell'app*, con tutto quello che la pagina è autorizzata
  a fare. Ora un indirizzo che arriva da lì è il server musicale e nient'
  altro: il pannello dentro la pagina non si apre per lui — il link in fondo
  alla pagina sì, in una scheda sua, come ha sempre fatto — e da dove viene
  l'indirizzo si ricorda insieme all'indirizzo, così al riavvio quello
  scritto a mano non torna a sembrare quello trovato sulla rete.

- **Una chiave scaduta di Audiobookshelf non spegne più la libreria.** Il
  cliente della libreria parlata ereditava il breaker e il retry senza saper
  distinguere un silenzio da un rifiuto: tre risposte «chiave non valida»
  (401) e per quindici secondi non veniva più contattato, quindi anche una
  ricerca che avrebbe funzionato rispondeva che la libreria non risponde. Ora
  un rifiuto conta come prova che il server c'è, ed è invece una richiesta
  persa a essere rifatta — la libreria si legge e non si comanda, quindi
  chiederle due volte la stessa cosa non fa niente due volte.

- **Due frasi dette insieme non si mescolano più.** Tutte le richieste di una
  stessa conversazione condividono un router — due schede del browser con lo
  stesso identificativo, oppure ogni comando di Home Assistant che non nomina
  un dispositivo — e ognuna ci scriveva lo stato del proprio turno mentre
  aspettava il server musicale. Una frase poteva tornare con i dati dell'altra:
  il pulsante «segnala questa frase» offerto a chi era stato capito benissimo,
  o un elenco sparito a metà scelta. Ora i turni di una conversazione vanno in
  fila, e la fila ha un limite: chi non riesce ad avere la conversazione entro
  i dieci secondi concessi a una frase risponde «sto ancora rispondendo alla
  frase precedente» invece di restare in attesa. Restare in attesa senza
  limite occupa un thread del server, e i thread sono 128: bastava
  un'automazione che ripete lo stesso comando per non far più rispondere
  nessuno. Le più letture che il riconoscitore dà della stessa frase, poi,
  contano come un turno solo anche per il tempo — dieci secondi in tutto, non
  dieci per lettura.

- **«Sì» suona dove è stata fatta la domanda.** «Metti Time da TIDAL in
  cucina», con TIDAL scollegato, chiede «Vuoi che la metta da Qobuz?» — e il
  «sì» faceva partire la musica sul player predefinito, non in cucina.

- **Un'alternativa mal trascritta non chiude più l'elenco aperto.** Il
  riconoscitore dà più letture della stessa frase e il router le prova in
  ordine: una lettura che non apriva nessun elenco cancellava quello aperto,
  così la lettura giusta subito dopo rispondeva «non c'è nessun elenco aperto».

- **Una risposta non parla più la lingua della richiesta precedente.** Sulla
  stessa connessione riutilizzata, una richiesta in inglese lasciava la lingua
  impostata per quella dopo: il pannello kid-safe rispondeva in inglese a chi
  stava usando l'app in italiano. Dietro un proxy che riusa le connessioni —
  l'ingress di Home Assistant — la richiesta precedente può essere di un altro.

- **Un server che dice «no» non è un server spento.** Dopo tre errori di fila
  il client smette per 15 secondi di contattare il server musicale, così un
  impianto spento non costa un timeout a ogni frase. Ma contava come «spento»
  qualunque errore: un token di Music Assistant scaduto, oppure tre ricerche
  lente dentro il tempo concesso a una frase, e per 15 secondi anche «pausa»
  rispondeva «Non riesco a contattare l'impianto» con il server perfettamente
  acceso. Ora contano solo i silenzi veri: un rifiuto (401, 403, una risposta
  che non ha senso) dimostra che il server c'è, e un timeout accorciato perché
  la frase aveva già speso il suo tempo dice che la frase era lenta.

- **Un comando non viene più eseguito due volte.** Se la risposta si perdeva
  dopo che il server aveva già eseguito il comando, il client lo ritentava:
  «alza il volume» saliva di due scatti, «prossima» saltava due brani, un album
  finiva in coda due volte. Ora si ritenta sempre solo ciò che non è mai
  partito (connessione rifiutata) e, se la richiesta potrebbe essere arrivata,
  solo i comandi che ripetuti non cambiano niente.

- **Una risposta malformata di Music Assistant non è più un «Errore interno».**
  Un JSON della forma sbagliata — una lista dove serviva un oggetto — sfuggiva
  a ogni controllo e arrivava all'utente come «Errore interno: 'str' object has
  no attribute 'get'». Ora è un rifiuto come gli altri, e una riga strana in un
  elenco viene scartata senza perdere le altre.

- **Music Assistant suona i brani della tua libreria.** Con la sorgente «auto»
  la libreria locale viene interrogata per prima, e un brano trovato lì
  rispondeva «Errore interno: 'id'»: il motore suona un candidato locale per
  id, e la riga del brano su Music Assistant non ne aveva uno. Succedeva con
  ogni titolo che la libreria conteneva.

- **Scegliere da un elenco di Spotify suona il brano scelto.** Con TIDAL come
  servizio predefinito, «quali brani dei Pink Floyd» su Spotify e poi «metti la
  2» chiedevano l'indirizzo del brano a TIDAL, che non lo conosce: all'impianto
  arrivava `playlist play None`, e la risposta diceva comunque «Riproduco».
  Ora la scelta va al servizio da cui è venuto l'elenco, e se un brano non si
  risolve in niente non si manda nulla e lo si dice.

- **Kid-safe riconosce l'artista di un album.** «Metti l'album The Marshall
  Mathers LP» con Eminem bloccato suonava: su Spotify il nome «… by Eminem»
  veniva ripulito del suo artista, e su Music Assistant l'artista non veniva
  proprio letto. Ora l'album porta con sé il suo artista, e il blocco lo vede.

- **Un brano da un album di Spotify suona quel brano.** «Metti Time dall'album
  The Dark Side of the Moon» suonava l'album intero: le tracce di un album
  Spotify non hanno un indirizzo diretto e venivano scartate, esattamente come
  capitava alle tracce di un artista prima che si imparasse a risolverle.

- **La pagina non si fida più di ciò che non ha scritto lei.** Quattro strade
  per cui testo arrivato dalla rete finiva nella pagina come codice, o
  l'impianto si ritrovava con più di quanto gli era stato chiesto:

  - la porta annunciata da una risposta UDP della discovery — a cui può
    rispondere qualunque dispositivo della rete — finiva così com'era
    nell'indirizzo ricordato e nel link a Material. Ora una porta che non è
    un numero tra 1 e 65535 non viene creduta, l'indirizzo ricordato ripassa
    dalla stessa verifica di uno scritto a mano, e il link viene sempre
    codificato per l'attributo in cui finisce;
  - i nomi dei servizi arrivano dal server musicale: nello script della
    pagina un `</script>` dentro un nome ne usciva, e il menu delle sorgenti
    li inseriva come HTML. Ora lo script li riceve con ogni `<` codificato e
    il menu li scrive come testo;
  - la copertina di una radio o di un plugin veniva letta per intero prima di
    guardarne il tipo, e un flusso annunciato come copertina finiva tutto in
    memoria a ogni aggiornamento del «in riproduzione». Ora il tipo si
    controlla prima di leggere, e più di 5 MB non si legge;
  - attraverso il pannello di Material, uno script servito dal server
    musicale poteva registrarsi come service worker davanti all'intera app.
    Il proxy non lo inoltra più (Material non ne usa), non concede il
    microfono a ciò che serve, e non trasforma un redirect in un indirizzo
    che porta su un altro host.

  La pagina dell'app e quella di configurazione non si lasciano più
  incorniciare da un altro sito (`frame-ancestors 'self'`): i clic dati da
  dentro una cornice arrivano come richieste della pagina stessa e passavano
  il controllo cross-site. Il pannello di Material, che è sulla stessa
  origine, resta com'è.

- **Fermare la musica non fa più sparire TIDAL per un giorno.** Il controllo
  che, alla richiesta successiva, decide se l'ultimo brano avviato ha davvero
  suonato leggeva un player fermo oltre il primo brano come «coda che scorre
  senza suonare». Bastava saltare due brani e fermare dal telecomando o da
  Material: un'ora dopo «metti…» rispondeva «TIDAL non è collegato», e il
  marchio restava 24 ore, salvato su disco. Ora si marca solo un player che
  dice «play» e non avanza, e solo se lo si legge entro dieci minuti
  dall'avvio: più tardi la lettura racconta la serata, non quell'avvio.

- **Un player scollegato non è un servizio scollegato.** Uno Squeezebox
  staccato dalla presa accetta la coda e resta fermo, e questo veniva letto
  come silenzio del servizio: «TIDAL non è collegato», poi lo stesso su Qobuz
  al secondo tentativo, e un giorno di esclusione per tutti e due. Ora il
  client riporta se il player è collegato (`player_connected` su LMS,
  `available` su Music Assistant), e la risposta è «Il lettore non risponde:
  è spento o scollegato», senza marchi e senza ritentare altrove.

- **Un disco pieno non rompe più una richiesta.** Se `services.json` non si
  poteva scrivere, l'eccezione arrivava fino alla risposta («Errore interno»)
  e saltava il passaggio che toglie dalla coda il brano muto. Ora
  l'impossibilità di salvare si scrive nel log, e quello che l'app ha imparato
  vale fino al riavvio.

- **La pagina di configurazione non cambia più un server che non è suo da
  cambiare.** La casella «prova questo indirizzo» non chiede credenziali, e
  quindi non l'ha a disposizione solo chi guarda la pagina: qualunque
  dispositivo della rete può scriverci. Finché la pagina restava aperta — dopo
  un blackout, o con l'add-on partito prima di Music Assistant — un indirizzo
  mandato lì sostituiva anche quello fissato con `--backend-url`, e la prova di
  quell'indirizzo portava con sé il token di Music Assistant, consegnandolo a
  chi rispondeva.

  Ora un indirizzo di configurazione non si sostituisce dalla pagina (403),
  che infatti non mostra più la casella e dice che l'indirizzo viene dalla
  configurazione. Anche un server che ha già risposto resta quello (409): in
  quello stato la casella era già nascosta. Resta correggibile, come prima,
  l'indirizzo ricordato che ha smesso di rispondere.

- **Un player scollegato non basta a finire la configurazione.** LMS elenca
  anche i player che non sente da tempo, con `connected: 0`; se uno di questi
  era in cima alla lista, l'app partiva puntata su un apparecchio che nessuno
  può sentire, e la pagina «accendi un player» non compariva mai. Ora contano
  solo i player collegati, sia per finire la configurazione sia per scegliere
  quello predefinito.

- **Anche il menu a tendina scrive i servizi come li dice la voce.** Restava
  una tabella, `SERVICE_NAMES = { tidal: "TIDAL", qobuz: "Qobuz" }`, dentro il
  JavaScript della pagina: una tabella che per costruzione poteva conoscere
  solo i servizi di LMS. Su Music Assistant il selettore della sorgente
  scriveva `apple_music` mentre la risposta parlata aveva già imparato a dire
  «Apple Music» — la stessa cosa chiamata in due modi nella stessa schermata.

  Ora le etichette gliele manda il server, che le chiede al client come le
  chiede per parlare, e nella pagina non c'è più nessuna tabella di nomi.
  Con LMS non cambia niente: «TIDAL» e «Qobuz» erano e restano quelli.

- **Il nome di un servizio lo dice l'impianto che ce l'ha.** Le frasi che
  nominano un servizio a voce — «TIDAL non è collegato», «da Qobuz», «la
  libreria ce l'ha ma il plugin è scollegato» — risolvevano quel nome contro
  la tabella dei servizi di LMS anche quando l'impianto era un Music
  Assistant. Un provider di MA in quella tabella non c'è, e la tabella
  ripiegava sul nome grezzo: usciva «apple_music non è collegato», cioè la
  chiave di configurazione letta ad alta voce al posto del nome. Ora
  l'etichetta si legge dall'oggetto servizio del client — `ServiceSpec.label`
  su LMS, `MAService.label` su Music Assistant — e si sente «Apple Music non
  è collegato».

  Con backend LMS non cambia una parola: lì la tabella era già quella giusta.

- **`--services` è misurato sull'impianto che hai, non su LMS.** Con
  `--backend musicassistant`, un provider legittimo di quel server veniva
  rifiutato all'avvio come «non valido», e l'elenco di alternative stampato
  sotto era quello di LMS: due liste sbagliate nella stessa riga, prima ancora
  che l'app fosse partita una volta. Ora la domanda va al backend attivo — la
  tabella fissa su LMS, i provider configurati su Music Assistant, **accesi o
  no**: un servizio spento non è un nome scritto male, e rifiutare di avviare
  l'assistente vocale mentre si ri-autentica TIDAL sarebbe raccontare un
  disservizio come un refuso.

  **È un cambio di comportamento.** Su MA un nome che prima passava perché per
  caso stava nella tabella di LMS ora viene rifiutato se quel server non ce
  l'ha, e un nome che quel server ha viene accettato. E se il server alla
  domanda non risponde, `--services` non valida niente invece di rifiutare
  tutto: quella riga esiste proprio per scavalcare un rilevamento che fa i
  capricci, e uno scavalco che ha bisogno del rilevamento non serve a nulla.
  Quando la domanda non si può proprio fare, l'avvio lo dice invece di tacere:
  da qui un token sbagliato e un server occupato si assomigliano.

- **Un servizio col trattino basso nel nome si può dire a voce.** Conseguenza
  della riga qui sopra: ora che `--services` accetta i provider di Music
  Assistant, «metti Time da Apple Music» deve arrivare dove uno se lo aspetta.
  Il nome scritto è `apple_music` e quello detto è «apple music», e finché si
  cercava solo la forma scritta la frase non veniva riconosciuta come una
  richiesta di sorgente affatto: rispondeva la libreria locale, senza dire che
  la sorgente nominata era stata ignorata.

- **Il prezzo della riparazione del verbo, scritto invece che scoperto.** La
  riparazione del primo verbo mal sentito («Matti» → «metti») ha un costo noto:
  una parola vera a una modifica dal verbo viene riparata come se fosse il
  verbo. Era dichiarato per l'italiano («letti sfatti» → «metti sfatti») e
  taciuto per le altre quattro lingue, dove vale uguale — misurato:
  «pay the bill» → «play the bill», «mes amis» → «mets amis», «jour de fete» →
  «joue de fete». Ora è scritto dove sta la regola, e un test lo tiene visibile:
  se qualcuno stringe il criterio, quel test cade e la decisione diventa
  esplicita.

  **Niente è cambiato nel comportamento**, ed è il punto: la soglia è tarata
  sulle 24 registrazioni di `tools/asr_titles_bench.py` (da 10 comandi su 24
  che arrivavano alla ricerca a 23), e stringerla senza rifare quella misura
  scambierebbe un guadagno misurato con un timore ipotetico. Alzare il pavimento
  a cinque lettere, per dire, salverebbe l'inglese «play» e ucciderebbe il
  francese «mets» e lo spagnolo «pone».

- **Un impianto irraggiungibile non è un nome di stanza sbagliato.** Con il
  server musicale momentaneamente giù, la lista dei lettori tornava vuota e
  *ogni* stanza smetteva di risolversi: un comando dal satellite in cucina
  riceveva «Non ho nessun lettore che si chiami Cucina, o non è collegato.
  Controlla i nomi dei lettori» — cioè un'interruzione di rete raccontata a
  tutta la casa come un errore di configurazione, che manda qualcuno a
  controllare nomi che non erano mai stati sbagliati. Lo stesso comando *senza*
  stanza rispondeva già la cosa vera: «non riesco a contattare l'impianto».

  `player_for_room` ora legge la lista da `players()`, che solleva, invece che
  da `_players_safe()`, che risponde vuoto; e chi chiama distingue i due fatti.
  «Quella stanza non esiste» resta quello che era — un server che risponde
  benissimo e non ha nessun Bagno va detto com'è.

- **`auto` ora vuol dire «i servizi che questa casa possiede», non «i plugin
  installati».** Era la domanda sbagliata, e la giornata l'ha dimostrata due
  volte sullo stesso impianto: un TIDAL il cui abbonamento è finito e uno
  Spotty senza account restano installati, rispondono al menu, rispondono alla
  ricerca — e non suonano. Chi si trovava in quella situazione doveva
  configurare a mano `--services`, cioè dire all'app una cosa che l'app poteva
  vedere da sé.

  Ora la vede, e **se la ricorda tra un riavvio e l'altro**: il verdetto sta in
  `<dati>/services.json`, accanto alla licenza. Non è configurazione, non si
  edita, e cancellarlo non rompe niente — si torna a impararlo al prezzo di una
  riproduzione muta. All'avvio il server dice ad alta voce quali servizi ha
  smesso di proporre, perché un servizio che sparisce in silenzio dalle
  risposte è la cosa che una casa deve sapere, non scoprire.

  Tre modi di uscirne, e due sono più veloci dell'orologio: **nominare il
  servizio** lo azzera subito («metti X da tidal» riprova davvero — è quello
  che dirà chi si è appena abbonato), **un secondo di audio** lo azzera come
  prova di vita, così un marchio preso durante un singolo intoppo di rete non
  sopravvive alla prima nota suonata, e in mancanza d'altro scade da solo dopo
  **24 ore** (`PLAYBACK_MISS_TTL`). Un servizio marchiato che sia rimasto
  l'unico viene comunque provato: il router non ha mai rifiutato di chiedere a
  chi era l'unico da chiedere.

  **La terza forma di silenzio**, quella di Spotty: dice `play` e non avanza
  mai. Non si può distinguere da uno stream che bufferizza senza aspettare più
  dei tre secondi che il buffer si prende, quindi non si aspetta: si chiude il
  verdetto **alla richiesta successiva** (`settle_pending`), dove il tempo è
  già passato da solo. Costa una lettura di stato nel turno che segue una
  riproduzione, e zero attese sulla conferma. Quel verdetto guarda i secondi
  suonati, non la posizione in coda: **un player fermo non è una prova**,
  perché è anche quello che lascia un brano finito o fermato da qualcuno, e
  leggerlo come guasto marchiava un servizio sano ogni volta che una canzone
  finiva. Ed è per player: in multi-stanza, il comando che arriva dal salotto
  non chiude il conto aperto in cucina.

  `server.py` sarebbe arrivato a 412 righe, oltre il tetto di 400 con il
  ratchet che vieta nuove eccezioni, quindi esce `localvoice/cli.py`: la lista
  delle opzioni è un elenco, e cosa il server ne fa è un'altra cosa. `server.py`
  scende a 338.

- **Venti brani in coda e nessuno che parte: lo stesso silenzio, un ramo più
  in là.** Il controllo introdotto qui sotto guardava solo il *modo* del
  player, e per un brano solo basta: se non parte, il player è a `stop` un
  terzo di secondo dopo. Per «canzoni di Gigi D'Agostino» no. Venti brani
  entrano in coda, il player li attraversa fallendone uno ogni ~170 ms, e per
  tutto quel tempo resta `mode=play`: a 0,6 s il controllo non vedeva niente,
  e l'app diceva «Riproduco la musica di Gigi D'Agostino» a una stanza muta.
  Misurato sull'impianto: la coda era arrivata all'**indice 19 su 20 con
  l'elapsed ancora a zero**.

  Quindi `now_playing_info()` ora riporta anche **posizione nella coda** e
  **secondi suonati** (tutti e due i backend; l'LMS manda l'indice come
  stringa), e il silenzio ha due forme invece di una: player fermo, oppure
  coda che ha lasciato il punto di partenza senza suonare un secondo di
  niente. La soglia è due brani e non uno di proposito: un brano singolo non
  disponibile — i diritti scaduti in un paese — fa avanzare la coda di uno e
  poi suona, e dare la colpa al servizio sarebbe una bugia peggiore di quella
  che questo controllo esiste per togliere.

  Il controllo copre ora anche gli altri avvii che ne erano scoperti — album,
  playlist, artista — e non la libreria locale: un client è sempre puntato a
  *qualche* servizio, e un file locale che non parte non è colpa di TIDAL. Per
  le righe che un servizio ha importato in libreria c'è `blocking_service`,
  che legge l'url della riga e sa di chi è l'audio.

- **«Disponibile» ora vuol dire «sa suonare», non «sa cercare».** La regola
  c'era già e non è cambiata: se la frase non nomina un servizio si usa quello
  predefinito, e se quello non è disponibile si passa al primo della lista che
  lo è — silenziosamente, ma mai di nascosto, perché la conferma porta il tag
  «… da Qobuz». Quello che non funzionava era la parola *disponibile*: si
  misurava con `can_search()`, e un plugin col token scaduto quel test lo passa
  a pieni voti. Risultato: con TIDAL muto e Qobuz perfettamente in salute, la
  richiesta veniva consegnata a TIDAL e Qobuz non veniva nemmeno preso in
  considerazione.

  Ora la domanda è `can_play()` — sa cercare **e** non ha appena suonato il
  nulla (`note_playback_failure`, dal controllo qui sopra). Tre conseguenze:
  la richiesta in corso prosegue da sola verso il primo servizio che sa
  suonare, invece di fermarsi a spiegare; quella dopo non ricompra la stessa
  scoperta, perché il marchio dura un minuto
  (`player/silence.py::PLAYBACK_MISS_TTL`, scritto una volta per tutti i
  backend come la resilienza lì accanto) e una
  seconda riproduzione muta costerebbe di nuovo una coda sostituita e una
  stanza zitta; e le righe che un servizio ha importato in libreria seguono la
  stessa regola, perché anche quelle sono audio che deve andare a prendere lui
  (`blocking_service`).

  **Nominare un servizio resta un'altra cosa.** «metti X da tidal» non viene
  dirottato: toglie il marchio e riprova davvero — è quello che dirà chi ha
  appena rimesso a posto il token — e se il silenzio si ripete la risposta è
  una domanda, non una sostituzione: «TIDAL non è collegato. Vuoi che la metta
  da Qobuz?». Con nessun altro servizio in grado di suonare non c'è niente da
  offrire, e resta il fatto nudo.

- **Un brano che non parte non è più «Riproduco».** Quando il plugin di un
  servizio perde il token — TIDAL lo fa spesso — la ricerca continua a
  funzionare benissimo: il menu risponde, «bla bla bla» torna con Gigi
  D'Agostino, l'url sembra suonabile. È l'audio a rispondere `401`. L'LMS
  accetta il brano, il player torna subito a `stop`, e Vivavoce diceva
  «Riproduco Bla Bla Bla di Gigi D'Agostino» a una stanza muta, lasciando in
  coda una traccia che non suonerà mai.

  `can_search` non poteva accorgersene: interroga la metà del plugin che
  funziona ancora. È anche il motivo per cui `blocking_service`, che protegge
  le righe che un servizio ha importato in libreria, lasciava passare proprio
  questa. Ora, dopo aver fatto partire un brano in streaming, l'app chiede al
  player se l'audio è davvero arrivato: se il player ha già smesso, la risposta
  diventa «TIDAL non è collegato» — la frase che l'app usa già per un servizio
  scollegato — la coda che non suonerà viene svuotata, e il risultato porta un
  `kind` suo (`playback.STREAM_OFFLINE`), così chi lo riceve non lo confonde
  con «non ho trovato niente». Il pezzo nuovo sta in `engine/playback.py`, che
  è la domanda «e poi è partito davvero?» tenuta insieme in un posto solo.

  **Misurato sull'impianto vero**, perché la differenza sta tutta nei tempi: un
  `tidal://` col token scaduto legge `mode=play` una volta sola e 0,33 s dopo è
  tornato a `stop` per sempre; un `qobuz://` sano resta `mode=play` e tiene
  l'elapsed a zero per tre secondi buoni mentre riempie il buffer. Il segnale
  quindi è il **modo**, non il tempo trascorso: leggere l'elapsed avrebbe
  dichiarato morto ogni stream che stava soltanto bufferizzando. L'attesa è di
  0,6 s (`playback.PLAYBACK_SETTLE`), e sulla strada buona si spende con la
  musica che sta già suonando.

  Quello che **non** fa, dichiarato: non cambia servizio da solo — chi ha
  chiesto TIDAL riceve una risposta su TIDAL, non una sostituzione silenziosa;
  non tocca la libreria locale; e non dice niente quando è il player a smettere
  di rispondere, perché un hi-fi che sparisce è un fatto diverso da un servizio
  scollegato e ha già le sue parole.

- **«Matti» non è un nome, è «metti» sentito male — e buttava via il comando.**
  Chi usa il riconoscimento vocale locale ha avuto per mesi un difetto che dal
  di fuori sembra incompetenza dell'app: dici «metti Comfortably Numb dei Pink
  Floyd», Whisper trascrive **«Matti** Comfortably Numb dei Pink Floyd» — con
  il titolo perfetto — e Vivavoce risponde «non ho capito». Il router aggancia
  i comandi sul verbo; un verbo di cinque lettere sentito con l'altra vocale
  non aggancia niente, e la ricerca non parte mai, pur avendo in mano la
  risposta.

  Ora, **e solo dopo che ogni altra lettura ha rifiutato la frase**, il router
  prova a rimettere a posto il primo verbo e a instradare una seconda volta.
  Con il microfono del browser, che di alternative ne restituisce diverse, la
  riparazione arriva perfino più tardi: un primo giro prova le trascrizioni
  come sono arrivate e solo se **nessuna** aggancia se ne fa un secondo
  riparandole. L'ordine non è pignoleria — riparando subito, «Matti Creep»
  vincerebbe su «metti Creepshow», cioè una trascrizione prima ma peggiore
  batterebbe quella giusta, che è l'esatto contrario del motivo per cui le
  alternative vengono provate.
  La regola non è nuova: è quella della parola chiave
  (`engine/wakematch.py::token_matches` — uguale, prefisso quasi completo, o al
  massimo una modifica), perché è la stessa domanda, un sì/no su una parola
  corta. Sta nel fallback per una ragione precisa: così nessuna frase che oggi
  funziona può cambiare comportamento, e «letti sfatti» non diventa un comando
  finché il router ha qualcos'altro con cui leggerlo.

  **Misurato, non stimato**, su 24 registrazioni vere fatte per l'occasione:
  da **10 comandi su 24** che arrivavano alla ricerca a **23**, punteggio medio
  del matching da 0,349 a 0,795. E non è una questione di modello: `small`,
  `medium` e `large-v3-turbo` sbagliano tutti e tre lo stesso verbo e prendono
  tutti e tre gli stessi titoli — `medium` in particolare è identico a `small`
  fino al terzo decimale a 2,8 volte il tempo di decodifica. Il banco che l'ha
  misurato resta nel repo: `tools/record_titles.py` registra le frasi,
  `tools/asr_titles_bench.py` le trascrive e le conta.

  Vale per tutte e cinque le lingue: `PLAY_VERBS` entra nel contratto dei
  language pack (`localvoice/lang/__init__.py`), accanto a `MOOD_WORDS`.
  Quello che **non** ripara, dichiarato: i verbi di due parole («fai partire»),
  le parole a due modifiche di distanza («Mattie», che nelle registrazioni
  compare e resta fuori), e i verbi sotto le quattro lettere — a tre caratteri
  una sola modifica confonde lo spagnolo «pon» con «con», «son», «por», e la
  tolleranza costerebbe più di quanto rende.

### Internal

- **Il motore chiede all'impianto cosa sa fare, prima di offrirlo.** La
  tabella delle capacità la dichiarava ogni backend e non la leggeva nessuno:
  un impianto con gli altoparlanti e nessun catalogo avrebbe risposto a
  «metti Time» con un errore interno, che all'ascoltatore arriva come «non
  riesco a contattare l'impianto» — una bugia su un impianto che risponde
  benissimo. Ora ogni ramo che offre qualcosa chiede prima, e quello che
  l'impianto non sa fare lo dice in tutte e cinque le lingue: cercare, la
  libreria locale, i preferiti, i generi e gli anni, il timer, le stanze. Con
  LMS e Music Assistant non cambia nulla — sanno fare tutto — ed è il
  presupposto per aggiungerne uno che sa fare meno.

- **`engine/lms.py` non è più un file da 1317 righe.** Era l'unico esentato
  dalla regola che questo repo dà a se stesso — 400 righe per file — e
  l'esenzione era lì da quando la regola è nata. Ora il client LMS è sei file:
  il client (il filo, i cloni per servizio e per stanza, l'elenco dei player),
  la tabella dei servizi, e un mixin per ciascuna delle quattro cose che quel
  client sa fare — camminare il feed di un plugin, chiedergli un catalogo,
  leggere il disco locale, comandare la riproduzione. Nessun comportamento
  cambia: `LMSClient` ha esattamente gli stessi metodi con le stesse firme, e
  ogni nome che si importava da `lms` si importa ancora. La lista delle
  esenzioni è vuota, e un test la tiene vuota.


- **Il cuore AGPL parte davvero senza `pro/`.** `licenses/README.md` presenta
  questo repository come open-core — tutto AGPL-3.0 tranne `localvoice/pro/`,
  e la metà libera dovrebbe essere un programma che funziona da solo. Non lo
  era: quattro import di `pro.*` erano nudi, e un checkout della sola metà
  libera moriva all'avvio con `ModuleNotFoundError`, prima della riga che
  avrebbe spiegato cosa mancava. Ora ogni import è protetto (kid-safe e
  multi-stanza in `localvoice/pro_features.py`, i motori audio in
  `audio_engines.py`), la funzione assente vale `None` — che è esattamente
  come si comporta da sempre un'installazione senza licenza — e l'app lo dice
  all'avvio. `tests/test_core_without_pro.py` nasconde il pacchetto e verifica
  che l'app importi, risponda e serva la pagina.

- **C'è un linter, ed è verde.** `engine/actions.py` portava un
  `# ruff: noqa` da prima che ruff esistesse nel progetto: il riferimento
  c'era, lo strumento no, e `uv run ruff check` rispondeva «comando non
  trovato». Ora ruff è nel gruppo `dev`, configurato in `pyproject.toml`
  (`E`, `W`, `F`, `B` — difetti, non gusti; riga a 100 colonne, che è la
  larghezza che questo repo scrive davvero) e girato in CI accanto ai test di
  packaging. `tests/test_packaging.py` verifica entrambe le metà, perché un
  riferimento a uno strumento che nessuno può eseguire si legge come un
  invariante e non lo è.

- **Il prefisso `SQUEEZESAY_` ha una data.** «Per un rilascio», diceva il
  commento, ed è rimasto per quattro. Esce con la **1.1.0**, il primo rilascio
  dopo il lancio pubblico, e l'avviso di deprecazione adesso lo dice.

- **Il test degli endpoint della licenza usa `live_server()`**, come tutti
  gli altri, invece di montare a mano un `ThreadingHTTPServer` che non è la
  classe con cui l'app gira (e che perdeva un thread se un'asserzione
  falliva prima del `finally`).

- **`PRIVACY.md` elenca il download del modello Vosk.** Due punti del
  documento dicevano già «elencato sotto»; sotto c'era solo Whisper.

- **`CLAUDE.md` non dice più che `set_lang` è globale di processo.** È una
  `ContextVar`: due richieste concorrenti in due lingue non si mescolano, e
  quello che davvero attraversa è una connessione keep-alive.

## 0.6.0 — September 2026

### Removed

- **L'app di Home Assistant non dichiara più armv7.** Home Assistant ha tolto
  le architetture a 32 bit con la 2025.12, e il loro registro lo conferma
  senza bisogno di crederci sulla parola: le basi amd64 e aarch64 vengono
  ricostruite (3.21 a giugno 2026, 3.22 ad agosto), quella armv7 è ferma al
  2025-11-21 su **ogni** tag Alpine e dalla 3.23 non esiste. L'app veniva
  quindi offerta a macchine che non possono far girare un Home Assistant
  aggiornato, e costruita per loro da una base non aggiornata da dieci mesi.

  Il prezzo non era la gamba di CI, che costava tredici secondi. Era che
  quella riga parlava a Supervisor che non la sentono più: su una macchina a
  32 bit, dalla 2025.12, il Supervisor smette di aggiornare le proprie
  informazioni sugli aggiornamenti, e lì non arriva più niente — né una nuova
  app né una nuova versione di una già installata. Dichiarare armv7 non
  teneva aperta una porta: la disegnava su un muro.

  Quello che togliere armv7 **non** sblocca è preinstallare il riconoscimento
  vocale locale dentro l'immagine dell'app, che sembrava il vincolo e non lo
  era. L'immagine è Alpine, cioè musl, e né CTranslate2 né onnxruntime
  pubblicano wheel musllinux: `pip` non li trova nemmeno su amd64, nemmeno con
  l'indice musl di Home Assistant già in catena, e Alpine non li impacchetta.
  Quella porta la chiude la libc, non l'architettura.
  `test_addon_declares_only_arches_it_can_actually_build_for` resta comunque:
  la lista `arch:` va tenuta onesta a prescindere da quale vincolo la stringe.

  **Fuori dall'app non cambia niente.** L'immagine Docker pubblicata copriva
  già solo amd64 e arm64, un Pi a 32 bit se la costruisce da sé, e la parola
  chiave lato server continua a installarsi lì perché vosk pubblica la wheel
  `armv7l`. Niente di tutto questo passa dalla lista `arch:` dell'app.

### Internal

- **La base dell'app sale ad Alpine 3.23**, da 3.21. È la prima cosa che
  togliere armv7 sblocca davvero, anche se piccola: la 3.23 è esattamente il
  tag che su armv7 non esiste, e finché quell'architettura era dichiarata
  `build.yaml` non poteva nominarlo. Dentro l'immagine cambia una dipendenza
  sola — `py3-cryptography` da 44.0.0 a 46.0.7, che serve a generare il
  certificato self-signed e a nient'altro — e Python resta il 3.12. Provata
  su entrambe le architetture prima del commit, con gli stessi controlli del
  job `addon`: l'immagine parte, scrive il certificato, risponde in HTTPS,
  riporta l'architettura giusta da `uname -m` e la versione giusta letta da
  dentro.

- **L'immagine dell'app Home Assistant non la costruiva nessun job, su nessuna
  architettura.** Il job `docker` costruisce l'immagine standalone, che con
  quella dell'add-on non ha quasi niente in comune — basi Alpine del Supervisor
  invece di `python:3.12-slim`, `apk add` invece di pip, sorgente scaricato da
  un tag invece che copiato dal checkout — quindi
  `test_addon_declares_only_arches_it_can_actually_build_for` ragionava sul
  fatto che armv7 fosse costruibile appoggiandosi a un argomento che nessuna
  build aveva mai controllato — ed è andando a controllarlo che è saltata
  fuori la ragione per togliere armv7, qui sopra. Ora la costruiscono due
  job, su ogni architettura dichiarata, sotto QEMU: `ci.yml` a ogni push,
  dall'ultimo tag che **esiste** —
  fra un rilascio e l'altro la versione in `config.yaml` non è ancora taggata e
  il Dockerfile prende un 404 apposta, quindi lì si prova ciò che dipende da
  monte, cioè che le basi del Supervisor esistano ancora e che
  `apk add python3 py3-cryptography` si risolva ancora su ognuna — e
  `release.yml` sul tag, dalla versione in uscita, che è la sola occasione in
  cui viene costruito esattamente il tarball che scaricherà il Supervisor,
  prima che lo scarichi qualcuno.

- **Ogni gamba avvia il container, non si ferma alla build.** Su
  un'architettura straniera quello che si rompe è il codice nativo, e si rompe
  quando gira, non quando viene copiato: il job confronta `uname -m` con
  l'architettura che credeva di costruire, controlla che py3-cryptography abbia
  davvero scritto il certificato, e rilegge la versione da **dentro**
  l'immagine — un tag che punta al commit sbagliato si costruisce benissimo e
  produce un'immagine che si chiama in un altro modo.

- **Le architetture esistono in un posto solo.** `tools/ci_addon_matrix.py` le
  ricava da `ha-addon/config.yaml` e `ha-addon/build.yaml`, i due workflow
  condividono i passi via `.github/actions/addon-image`, e in ognuno resta solo
  ciò che differisce davvero: quale versione costruire. Aggiungere
  un'architettura è una riga in ognuno di quei due file e nessuna sotto
  `.github/`. Lo script è di sola libreria standard perché quel job non
  installa niente, ed è tenuto onesto da un test che rilegge gli stessi due
  file con PyYAML e pretende la stessa risposta. `RELEASING.md` diceva il
  contrario di tutto questo («CI does not build the add-on image») e mandava a
  costruirla a mano dopo il tag: il passo 6 ora racconta quello che succede.

## 0.5.0 — September 2026

### New

- **Vivavoce non è più legato a un LMS: ora sa pilotare anche Music
  Assistant.** Fino a qui il sistema musicale era uno solo, e non per una
  scelta di design: `engine/lms.py` era insieme il client e l'interfaccia, così
  chi ha un impianto diverso non poteva usare nulla di quello che questo
  progetto fa — il riconoscimento del titolo, la scelta dell'edizione giusta,
  il «quale intendi?» — pur essendo tutto indipendente da *chi* poi fa suonare
  la musica. Adesso il motore parla a un'interfaccia
  (`engine/player/protocols.py`) e LMS è **un** backend fra altri.

  Due protocolli e non uno, perché un altoparlante non è un catalogo: quello
  che fa un dispositivo — pausa, volume, coda — e quello che fa un catalogo —
  cercare, risolvere, disambiguare — sono cose diverse, e ogni backend dichiara
  quali sa fare (`Capabilities`). Il motore chiede prima di offrire, così un
  lettore che non sa cercare lo dice invece di far passare l'assenza per un
  guasto.

  Il secondo backend è **Music Assistant**: `--backend musicassistant`,
  `--backend-url http://<ip>:8095` e `--backend-token` (il token si crea in
  Music Assistant sotto Impostazioni → Profilo), con i gemelli d'ambiente e le
  tre opzioni corrispondenti nell'app Home Assistant. Vale la pena anche per
  chi non ha Squeezebox: Music Assistant pilota da sé altoparlanti DLNA,
  Chromecast, Sonos e AirPlay, quindi puntandogli Vivavoce quelli diventano
  lettori comandabili a voce senza installare altro. Non serve nessuna
  dipendenza nuova — la sua API risponde anche su un semplice `POST /api`,
  quindi il core resta di sola libreria standard come è sempre stato.

  Due assenze, dichiarate perché sono assenze e non difetti: il pannello
  Material Skin non c'è (è un plugin di LMS) e non esiste un indice per anno,
  quindi «musica degli anni '80» ripiega su una playlist del servizio di
  streaming invece di pescare dalla libreria. Il default resta `lms` e non
  cambia niente per chi ha un LMS, auto-discovery compresa.


- **La parola chiave sul server è di nuovo quella scelta in casa.** Il motore
  server esisteva per togliere il beep che Android emette a ogni riavvio del
  riconoscimento continuo, e lo toglieva — ma insieme si portava via la frase:
  openWakeWord sente solo le poche frasi inglesi per cui spedisce un modello,
  quindi «niente beep» costava «Hey Jarvis» e il campo di testo spariva. Ora
  accanto c'è un secondo motore, Vosk a riconoscimento libero
  (`localvoice/pro/vosk_wake.py`, gruppo `wakeword-vosk`), che trascrive e cerca
  la frase nel testo: la frase torna a essere quella digitata, e vale per tutta
  la casa invece che per il singolo browser (`wakeword.json`, `GET`/`POST
  /wakeword/phrase`). Vosk vince quando è installato e ha un modello su disco;
  openWakeWord resta come ripiego dove è già in uso.

  Il modello (~47 MB per lingua) si scarica **all'avvio**, una volta, dentro la
  cartella dati — quindi in Docker finisce nel volume e sopravvive agli
  aggiornamenti, come quello di Whisper. All'avvio e non al primo uso, a
  differenza di Whisper, per una ragione precisa: la prima richiesta della
  parola chiave è un chunk audio da 320 ms dentro un flusso di chunk, e
  scaricare 47 MB lì dentro manderebbe la richiesta in timeout — un motore
  lento diventerebbe indistinguibile da uno rotto. Qui invece è una riga di
  progresso prima che il server accetti qualcosa, e un fallimento è un
  messaggio invece che un mistero: senza rete l'avvio prosegue, la parola
  chiave libera resta spenta e il resto non cambia.
  `--wakeword-no-download` lo disattiva per installazioni offline;
  `--wakeword-vosk-model` indica una cartella gestita a mano, e su quella non
  si scarica mai sopra.

  La scelta viene da un banco di misura, non da una preferenza. Sui 40,2 minuti
  di impianto acceso in sala registrati per l'occasione, la grammatica ristretta
  di Kaldi — l'idea ovvia, restringere il riconoscitore alla sola frase — ha
  fatto **21 falsi trigger all'ora**, sette su voce italiana e sette su
  strumentale: con due sole uscite possibili, l'audio ambiguo viene spinto verso
  la frase, e chitarra flamenca e Vivaldi diventano «vivavoce». A lessico pieno
  ce n'è stato **zero**. La grammatica sopravvive solo come oracolo del
  vocabolario, mai come decodificatore, e il docstring lo dice per iscritto
  perché è il tipo di cosa che qualcuno ricablerebbe.

  Misurato attraverso l'endpoint vero, in chunk da 320 ms come li manda
  `serverwake.js`: **15/15** in stanza silenziosa, **15/17** parlando sopra la
  musica, **0 falsi trigger** in 40 minuti di sala e **0 su 120 clip di
  quasi-parole** («vivace», «viva la vita», «prova la voce»…). RTF 0,10 e
  310 MiB — sotto il gate `MIN_RAM_GIB = 3.5` di `pro/asr.py`, quindi la parola
  chiave gira anche dove la trascrizione locale non ci sta.

- **Una frase che il motore non potrebbe mai sentire viene rifiutata quando la
  scrivi.** Kaldi produce solo parole del suo lessico, quindi «vivavoce» si
  attiva nell'83-100% dei casi e un nome inventato come «zorblax» nello **0%** —
  83 punti di scarto cambiando solo la parola, e nessun sintomo tranne «la
  parola chiave non funziona benissimo». `POST /wakeword/phrase` ora interroga
  il lessico prima di salvare e rifiuta dicendo *quale* parola non esiste. Il
  controllo è possibile solo leggendo un avviso che lo strato C++ scrive sul
  **file descriptor 2**: Vosk non espone API, i modelli small non spediscono
  `words.txt`, e una parola sconosciuta non solleva eccezione — il riconoscitore
  si costruisce contento e poi non si attiva mai. Il rifiuto vale per il motore
  server; il browser, che di lessico non ne ha, continua a sentire la frase, e
  infatti resta salvata in locale.

- **Spanish, the fifth language.** The page has offered `es-ES` to the
  microphone since read-back shipped, and picked a Spanish voice for it, and
  then answered in Italian. This is the pack (`localvoice/lang/es.py`) and the
  catalog (`engine/catalogs/es.py`) behind that choice. Three tests were
  already written against the gap and one of them said so in as many words —
  «Spanish is the last mic language without a catalog».

  Three things Spanish does that the other four do not, and each one decided a
  pattern rather than being translated into one.

  «para» is the stop verb and it is also the commonest preposition in the
  language. «música PARA dormir», «algo PARA cenar», «Para Todos los
  Públicos» — and the pause step is gated only on ¬is_play, so an unanchored
  `\bpara\b` paused the hi-fi on any bare phrase carrying the word, typed or
  picked from an open list. Half the mood vocabulary carries it. The word now
  lives only inside `DEV()`, where an article and a device noun have to follow
  it, which no preposition ever is; a lone «para» and «párala» are written out
  separately, anchored to the whole command.

  The pronoun welds itself onto the verb and moves the accent when it does.
  «ponme», «ponlo», «pónmelo», «súbelo», «quítala» are one word each, and the
  stress mark appears only once the clitic is there. French hyphenates and
  German keeps its particle at a distance; Spanish writes one word. Every verb
  in the pack is `acc()` plus a clitic cluster, and no verb is spelled twice —
  a stem written as "every vowel may carry an accent" already matches «súbe».

  The article is the whole difference between asking for music and pressing
  play. «pon música» is the ordinary way to ask for something to listen to;
  «pon la música» is ▶. French lets «mets musique» resume and pays for it;
  here the device builder requires the article and the first falls to the mood
  step, which is where it belongs.

  Two smaller ones. The inverted question mark survives `clean_command` —
  which strips a trailing «?» and leaves the «¿» welded to the first word,
  where it breaks every ^-anchored pattern at once — so it is stripped there,
  language-neutrally, rather than written into eleven patterns that would
  drift apart. And «de» now belongs to two languages: it is how French names
  an artist and how Spanish does. That is not the bug `engine/connectors/`
  exists for — that bug was one table matched by every language at once — so
  the two claims cost nothing, and the test that assumed one owner per
  connector takes a set now.

  What Spanish does not need, recorded because French needed it badly: no
  negation guard. «no pares», «no quites», «no apagues» are different words
  from «para», «quita», «apaga», and `\b` keeps them apart for free. Italian
  escapes the same trap the same way.

  Not included: the page chrome, which is Italian or English only, and the
  Home Assistant blueprint, whose sentence triggers are still Italian and
  English. The phrasings have not been reviewed by a native speaker, and no
  Spanish recogniser has been run against them.

- **Material Skin opens inside the page.** The link at the bottom used to send
  you to another tab: you got the queue, the covers and the browsing you were
  after, and you left Vivavoce — to say the next thing you had to notice you
  were in the wrong tab first. The microphone, which is the product,
  disappeared behind somebody else's interface. It now opens in a panel over
  the scrolling area, with the hero — knob, status line, text box — exactly
  where it was, so browsing and speaking are one visit.

  What makes it possible is a reverse proxy (`localvoice/lmsproxy.py`), and
  it has to exist: the page is HTTPS because a microphone on another device
  requires a secure context, the LMS is plain HTTP, and an `<iframe>` pointed
  straight at it is mixed content that the browser blocks without appeal. The
  artwork proxy has been solving that one `<img>` at a time since the
  now-playing card was written; this is the same idea for a whole application.

  Catch-all, not a prefix. Material asks for `/cometd`, `/jsonrpc.js`,
  `/music/`, `/imageproxy/`, `/plugins/` and `/settings/` by absolute path, so
  a rewritten prefix would break all of them: what this server does not answer
  itself is offered to the LMS instead. The guards did not need a line — the
  Host allow-list already ran ahead of every GET and the cross-site check
  ahead of every POST, so the proxied requests inherit both, and a page
  somewhere else that tried to reach `/jsonrpc.js` through here is refused
  exactly as it was. Two things that used to reach the old catch-all were
  pinned down first: `/static/` misses stay ours, and so does `/ca.pem` when
  there is no CA to hand out.

  It switches itself off. The panel appears exactly when the UI it would open
  lives on the LMS this app already talks to; point `--material-url`
  anywhere else and both the proxy and the panel go away, leaving the plain
  external link of before — which is also what a browser with no JavaScript
  gets. A locked kid-safe device is not shown the way in, the same as the
  voice commands, and with the same honesty: it is the interface being tidy,
  not a gate, since whoever knows the address still reaches it. The external
  link had that hole too, in plain sight.

  A review of the first cut moved six things before it shipped, all of them
  the proxy widening something the app had reasoned about narrowly.
  `do_GET` skips the cross-site check on the reasoning that triggering a
  read is harmless because the answer cannot be read back — true of this
  app's routes, false of a gateway to an interface that *acts* on GET
  (`/status.html?p0=power&p1=0`), and it would have been a new way in, since
  an `https://` page cannot reach the plain-HTTP LMS at all today. Proxied
  GETs are guarded now. Relayed bodies carry `nosniff`, because this origin
  now serves whatever the music server hands out. `Authorization` travels up
  and `WWW-Authenticate` comes back, so a password-protected LMS can still
  ask for its password instead of silently never loading. A redirect the LMS
  aims at itself is rewritten to a path, or the frame would be sent back to
  `http://` — the exact block the proxy exists to get around. A chunked
  request body is refused with a 411 rather than read as empty and left in
  the buffer for the next request on the connection to be parsed out of. And
  the panel's close button no longer goes through `history.back()`: browsing
  inside the frame adds entries to the joint session history, so after a few
  taps the button would have stepped around inside Material and looked dead.

  The one deliberate 5xx in this server lives here: an unreachable LMS is a
  502. A 404 would have made "Material isn't installed" and "the hi-fi is
  switched off" the same answer, and those are different rooms to walk to.

  Material Skin is Craig Drummond's, MIT-licensed, and **not one line of it is
  redistributed** — the plugin is already on your LMS and this only puts it
  under an address the page is allowed to frame. Credited in the panel and in
  `licenses/README.md`.

- **French, the fourth language.** Pick *Français* as the mic language and
  Vivavoce parses and answers in French: «mets Time de Pink Floyd», «coupe la
  musique», «arrête dans 30 minutes», «mets quelque chose de relaxant», «mets
  Time dans la cuisine». One pattern pack (`localvoice/lang/fr.py`), one
  message catalog, and a test suite of its own — the page already offered
  fr-FR to the microphone and already picked a French voice for it, and
  answered in Italian.

  Three things French does that none of the other three does, and each one
  decided a pattern rather than being translated into it:

  * **The accent is optional and the meaning is not.** The router matches what
    was said as it arrives, and `re.I` folds case but not accents, so
    «arrete la musique» typed into the box was not the same word as «arrête»
    — it fell past the stop step and searched the library for a record called
    "la musique". Every accented word in the pack is now built by one helper
    from its correct French spelling, so a review checks the French and the
    six vowel families come for free.
  * **The word that decides sits on either side of the object.** «monte le
    son» puts it in front, «mets la musique plus fort» puts it behind a verb
    that says nothing on its own — German's separable verb with French parts.
    And «son» is also the possessive, so it counts as the device only behind
    an article: «mets son dernier album» is a request to play.
  * **Politeness lands after the object, not inside the phrase.** «mets la
    radio s'il te plaît» asked the server for a station called "s'il te
    plaît"; «mets la deuxième stp» stopped being a pick. Every step that
    reads to the end of the sentence now ends at the end of the *command*.

  Not included: the page chrome, which is Italian or English only — a French
  session gets French answers inside an English page — and the Home Assistant
  blueprint, whose sentence triggers are still Italian and English. The
  phrasings have not yet been reviewed by a native speaker.

- **German, the third language.** Pick *Deutsch* as the mic language and
  Vivavoce parses and answers in German: «spiel Time von Pink Floyd», «mach die
  Musik aus», «schalt in 30 Minuten aus», «spiel etwas Entspannendes», «spiel
  Time im Wohnzimmer». One pattern pack (`localvoice/lang/de.py`), one message
  catalog, and a test suite of its own — no other module learned a word of
  German.

  Three things German does that neither Italian nor English does, and each one
  decided a pattern rather than being translated into it:

  * **The verb comes in two pieces.** «leg Time auf», «mach die Musik an» and
    «ich möchte Time hören» wrap the title in a verb and its particle, so the
    plain-verb pattern would have searched for "die Musik an". The split forms
    have their own pattern — the one English already uses for "put Dark Side
    on" — and the plain verbs deliberately do not list «leg»/«mach», which is
    what lets «spiel Wach Auf» keep its "auf".
  * **«mach» heads three different commands.** «mach lauter» is volume, «mach
    aus» is stop, «mach die Musik an» is play. The play reading is recognised
    only *with* its particle, so the other two stay reachable.
  * **The adjective changes sides.** «etwas Entspannendes» puts the mood after
    the marker noun, «etwas entspannende Musik» before it. Both reach the mood
    table; both still require the marker, so «stopp die entspannende Musik»
    keeps stopping the music.

  Not included: the page chrome, which is Italian or English only — a German
  session gets German answers inside an English page. The phrasings have not
  yet been reviewed by a native speaker.

### Fixed

- **«viva voce» non attivava «vivavoce».** L'ascolto continuo confrontava una
  parola sentita per ogni parola della frase, il che rende una frase di una
  parola incapace di corrispondere a due — e dove il riconoscitore mette lo
  spazio non lo decide chi parla. Sulle 32 registrazioni reali usate per il
  banco la frase è stata trascritta «viva voce» in **6 delle 29** pronunce
  effettivamente sentite: tutte scartate in silenzio. Contate a parte, sono 27
  punti in stanza silenziosa (73% → 100%) e 11 sopra la musica (71% → 82%). Ora
  il confronto si fa anche a parole incollate, nei due versi.

  Con un vincolo che è costato una seconda misura: se il numero di parole
  cambia, le lettere devono essere esatte. Perdonare *insieme* uno spazio
  spostato e una lettera sbagliata spende due tolleranze sullo stesso errore, ed
  è esattamente lì che passa una quasi-parola — sulle 120 clip di confusabili,
  «la vita e voce» si attivava, perché "vitavoce" dista un'edit da "vivavoce".
  Con la regola stretta: zero. La stessa regola vive ora in due posti che devono
  rispondere uguale, `engine/wakematch.py` e `static/js/wakeword.js`, ed è la
  ragione per cui il modulo Python esiste.

- **`licenses/MODELS.md` attribuiva ai modelli openWakeWord la licenza del suo
  codice.** Il codice è Apache-2.0; i **modelli pre-addestrati** sono
  CC-BY-NC-SA 4.0, per ammissione esplicita del progetto a monte («due to the
  inclusion of datasets with unknown or restrictive licensing as part of the
  training data»). Non è una sfumatura: quel motore sta dietro il livello Pro,
  cioè a pagamento. La pagina ora lo dice, con l'avviso in evidenza. Il motore
  Vosk che lo affianca non ha questo vincolo — `vosk-api` e i modelli small
  italiano e inglese sono Apache-2.0 — ma la scelta su cosa fare del ripiego
  resta da prendere, e non la risolve una correzione di documentazione.

- **The app would not start because the Squeezebox was off.** Two of the four
  ways `main()` could return 1 were not configuration mistakes at all: no LMS
  discovered on the network, and no player switched on. Both ended the
  process before it bound anything, so the web app — the only part of this
  anyone in the house ever looks at — never came up. The person who could
  have fixed it in ten seconds by reaching over and switching the hi-fi on
  saw a phone that would not load a page, while the diagnosis
  (`Nessun player trovato su …`) sat in a terminal on a machine in a
  cupboard.

  The server now binds first and explains itself second. Where it used to
  exit there is a small page on the real port
  (`localvoice/setupserver.py` for the deciding, `setuppage.py` for the
  saying) that names which of three things is missing — nothing found on the
  network, an address that does not answer, or an LMS answering with nothing
  switched on — and offers the address by hand for the first two. It also
  goes on looking by itself, so switching the player on is the whole repair:
  the page walks into the app with nobody typing anything.

  Three details that are the difference between this and a spinner. A
  remembered address is given up on after two silent probes and the network
  searched again, because a lease expires and an LMS moves — but an address
  given with `--lms` never is, since hunting the network for a server
  somebody already named is how you end up controlling the neighbour's. The
  network search runs on its own much slower clock than the address probe
  (`DISCOVER_INTERVAL` against `PROBE_INTERVAL`): one is a short connection,
  the other is a broadcast plus a unicast sweep of every subnet, and this
  loop can run all night — which is also why only the cheap half runs before
  the port is bound, so a first-ever start shows «sto cercando…» rather than
  an unresponsive address for half a minute. And `--player` still means what
  it always meant — the LMS has to answer, not the list has to be non-empty.

  `wait_for_players` is gone with it. It solved the same problem from the
  wrong side: it kept the process alive by refusing to return, which is the
  behaviour that kept the page from existing.

- **One spoken sentence could take twenty-five seconds to fail.** A turn is
  several sequential LMS round trips — `play_song` searches, plays, then asks
  what actually started; `play_local` runs three library searches plus a
  probe per candidate. Each was bounded by the client's 8-second socket
  timeout and nothing bounded their sum, so against a half-dead LMS a single
  command sat there through all of them and then answered with one
  undifferentiated "server unreachable". Against an LMS that was simply
  switched off it did that again for the next command, and the next, all
  evening.

  Three changes, in `engine/lms.py`, and each covers a case the others do
  not. `turn_deadline` gives the whole turn one budget (`Router.TURN_BUDGET`,
  ten seconds — the point past which a person has already decided nothing is
  going to happen); calls inside it get what is left, never more, and once it
  is gone the rest fail at once. A transport failure is retried **once**,
  because a dropped packet or an LMS caught mid-restart is not an outage — a
  well-formed answer we happen not to like is never retried, since asking
  again gets the same answer. And a breaker opens after three failed
  commands, so "the hi-fi is off" is learned once instead of re-timed-out per
  call; the cooldown lets exactly one probe through, and only a success
  resets the count, so a house that left the system off does not pay for the
  timeout twice a minute. The breaker is shared by `for_service()` and
  `for_player()` clones for the same reason the search-node cache is:
  whether the server answers is a fact about the server.

- **A plugin you had just logged in stayed "logged out" for another half a
  minute.** The search-node lookup was memoized for thirty seconds in both
  directions, and the two directions are not worth the same. A *found* node
  saves a round trip that is about to happen anyway — that is what the cache
  is for. A *missing* one saves nothing, because the caller gives up rather
  than asking again, and it costs the household the one thing this cache
  should never cost them: logging TIDAL into LMS, coming straight back, and
  being told again that it is not connected. Misses now expire in two seconds
  (`SEARCH_NODE_MISS_TTL`), which still collapses the duplicate lookups
  inside one turn, which is all the saving there ever was on that side.

  The other direction had no answer at all: a plugin logged out *since* we
  looked kept being handed a node id that no longer meant anything, and the
  failure was reported as "nothing found" rather than "not connected" — the
  one distinction `can_search` exists to make. A search that comes back with
  no categories at all now forgets the node, so the next call looks again.

- **One misheard letter in an artist's name was answered with "I couldn't
  find it".** «Comfortably Numb dei Pink Floid» scores 0.66 against Pink
  Floyd — under the bar for playing somebody's edition unasked, which is
  right — and the next line turned that into a flat refusal, with the exact
  record the household asked for sitting first in the results. A dropped
  diacritic does the same to half the Latin catalogue.

  "Not sure it is them" and "sure it is not them" are different findings, and
  only the second is a refusal. Between the two bars the candidates are now
  offered, nearest name first, so «la 1» is the whole repair; below the lower
  one (`NEAR_ARTIST_SCORE`) they really are other people — Vasco Rossi
  against The Beatles scores 0.07 — and "I haven't got it" stays the honest
  answer. Nothing plays without being asked for either way, which was the
  part that was already right.

- **"Microphone error: audio-capture".** The status line passed the browser's
  own error codes straight through, inside a translated frame — `network`,
  `audio-capture`, `not-allowed` — which is a sentence that tells a household
  nothing they can act on. Continuous listening giving up was worse: it said
  the code in brackets and then advised checking the microphone *and* the
  connection, one of which is always irrelevant. The small fixed vocabulary
  those two APIs actually raise now has a sentence each, in both languages
  (`static/js/micerrors.js`), naming the thing the person holding the phone
  could do about it. A code outside the table keeps its raw spelling rather
  than getting a generic apology: an unexplained code is still something to
  search for, and a confident wrong explanation is not.

- **The example commands disappeared for whoever needed them most.** The
  three chips and the source note went away on the first message — including
  a message that failed. So the person whose first attempt did not work was
  the one who lost the examples, for the rest of the session, with no way to
  get them back. They now stay until something has actually worked.

- **Hands-free listening woke itself up and then said it hadn't understood.**
  Switching on continuous listening starts the recogniser and *then* speaks
  the art. 50(1) notice — and that notice used to open with "Vivavoce,",
  which is the default wake word. So the loudspeaker said the wake word into
  the app's own live microphone, `commandAfterWake()` matched it, and
  everything after it — "assistente vocale automatico" — went to the router
  as a command. One unexplained "Non ho capito" per page load, before anybody
  had said anything.

  Fixed on both sides, because either alone is half a fix. The notice no
  longer names the product, which removes the collision that ships by
  default; and **the microphone now ignores whatever it hears while the app
  is talking**, which is the rule that holds for a wake word the household
  typed itself and for read-back speaking a reply. That gate reads
  `speechSynthesis.speaking` rather than counting `onstart`/`onend` events:
  those are not delivered everywhere (headless Chromium fires neither, iOS
  Safari drops them), and a counter that never comes back down would leave
  the wake word deaf for the rest of the page's life. It is bounded in the
  other direction too — Chrome has been known to leave `speaking` true
  forever after a cancel.

  Ignoring is not enough on its own, either: Chrome's continuous results are
  *cumulative for the session*, so the sentence the app spoke is re-delivered
  in every later event and would simply be acted on a moment after the room
  fell silent. What was heard through the speaker stays ignored for the rest
  of the session.

- **The spoken notice was startlingly loud.** It is a legal notice, not an
  answer to anything anybody asked, and it arrives the instant the microphone
  goes on. Now spoken below the read-back voice, and shortened to "Assistente
  vocale automatico." / "Automated voice assistant." Art. 50(1) asks that it
  be said plainly at the start of the interaction, not that it be the loudest
  thing in the room; `docs/ai-act.md` records the change.

- **One silent client could stop the whole HTTPS server.** Serving TLS by
  wrapping the *listening* socket — which is the obvious way to do it, and
  what `--cert/--key` did — puts the handshake inside `SSLSocket.accept()`,
  which is to say inside the accept loop, in the main thread, with no
  timeout. So a single client that opened a connection and then said nothing
  blocked every other device in the house, and it did not recover on its own:
  the connections queued behind it were still there, unanswered, when it went
  away. Browsers produce exactly such connections without being asked to —
  they preconnect and abandon — so in practice the page loaded once and every
  later request hung or was reset, and it looked like a certificate problem
  because the certificate is what you are thinking about when you first turn
  HTTPS on. The listening socket now stays plain and each accepted connection
  is wrapped in the thread that will serve it, bounded by the same timeout
  every other request has. A failed handshake — a browser sitting on the
  self-signed warning, a plain `http://` typed at the TLS port, a LAN scanner
  — now costs its own connection and nothing else, and no longer prints a
  stack trace for something that is not an error.

- **Dismissing the microphone prompt killed the microphone until reload.**
  Tapping *beside* the permission prompt rather than answering it is the
  easiest mistake there is to make here, and it ended the session: the button
  did nothing from then on, no prompt ever came back, and only reloading the
  page brought the microphone back — which was the tell, because a reload is
  precisely a new `SpeechRecognition` object. Chrome reports a dismissal by
  reporting nothing at all — no `onstart`, no `onerror`, no `onend` — and
  leaves the recogniser in its starting state, where every later `start()`
  throws `InvalidStateError`; that throw was swallowed, so nothing downstream
  ever learned the microphone had stopped working. A stranded session is now
  aborted and the start retried, so the second tap asks again. A denial on
  tap-to-talk also no longer switches continuous listening off: that teardown
  exists because a denied mic would restart-loop in wake mode, and it was
  unticking — and saving — a preference the user had set on purpose.

- **Read-back spoke the reply frame with the wrong voice.** The split between
  "the frame" and "the foreign terms" was right; the frame's language was
  hard-coded to Italian, so an English session heard "Playing" and "by" read
  out by an Italian voice, and only the title and the artist got an English
  one. The frame now follows the language the *server* answered in, which the
  page learns from the server (`window.VIVAVOCE_CFG.langs`) instead of
  guessing: it is not the page language — the chrome is Italian or English
  only — and it is not the mic language either, since a mic language with no
  catalog behind it (Spanish, French) is answered in Italian. German is what
  made this impossible to keep filing as a detail: its replies are German
  inside an English page, so neither of the two languages already on the page
  was the right one. One spoken string is deliberately left behind: the AI Act
  disclosure follows the page language, because there is no German version of
  it to read out.

### Changed

- **La scelta dei motori audio opzionali vive in `localvoice/audio_engines.py`.**
  Aggiungere il secondo motore di parola chiave ha spinto `server.py` oltre il
  tetto di 400 righe che il repo si dà (`tests/test_packaging.py`), e la
  cucitura è reale e non aritmetica: tutto quel blocco risponde a una domanda
  sola — *dato quello che è installato su questa macchina, cosa riesce a
  sentire l'app?* — ogni motore è opzionale, sondato invece che importato,
  degrada a un default funzionante, e deve dirlo ad alta voce, perché un motore
  spento in silenzio è il silenzio più caro che questa app possa produrre. Un
  test nuovo copre la giuntura che la separazione ha creato: la nota
  sull'architettura a 32 bit ora è un *parametro*, quindi poteva restare in
  ogni messaggio ed essere vuota su ogni macchina.

- **Il banco misura i frame che il prodotto manda davvero.** `sherpa_bench.py`
  spezzava l'audio in chunk da 300 ms con un commento che li diceva uguali a
  quelli di `serverwake.js`, che ne manda **320**. Non è cosmetico: stessa
  audio, stessa regola, 14/17 a 300 ms e 15/17 a 320, perché il partial che
  porta la frase cade su un confine di frame diverso. Una pronuncia su
  diciassette da sola è rumore; un banco che inquadra l'audio diversamente dal
  prodotto no.

- **`ERR_UNREACHABLE` is gone.** It was computed once at import, in whatever
  `DEFAULT_LANG` happened to be, while every live path called `msg()` against
  the per-request language — a self-acknowledged legacy shim that several
  tests still compared against. Nothing caught it because `ActionResult`
  subclasses `str`: a comparison against the frozen Italian sentence came
  back `False` rather than raising, so those tests only passed for as long as
  nobody switched language first. Callers ask for `msg("err_unreachable")`,
  and a test now checks the reply really does follow the turn's language
  through all five catalogs.

- **The remembered LMS address moved to `appdata`**, next to the data
  directory and the atomic writes it was already using, and `_lms_reachable`
  went with it — the setup flow probes every address it is handed, so
  checking the remembered one twice was only a slower way to be wrong.

- **The connectors are per language now** (`engine/connectors/`), instead of
  one pile every language matched against at once. French is what made the
  pile impossible: its artist connector is «de», the split takes the *last*
  connector in the phrase, and «la canzone di Marinella di De André» went
  looking for a singer called «André». One module per language, and what a
  module declares is what that language matches: «di» is Italian's, «by»
  English's, «von» German's, «de» French's, and none of them is everyone's.

  This is a behaviour change and not only a move — the reason «von» was left
  in the pile the first time round. A request phrased in one language and
  heard by a recogniser set to another is no longer split into title and
  artist: «Comfortably Numb von Pink Floyd», said to an Italian mic, is one
  long title now. The search still runs on the full text, so the request is
  still answered; what it loses is the hint that ranks the results. That is
  the trade, and it is paid for by the mic: `Router.handle` sets the language
  before anything parses, so the language in flight is the language of the
  phrase far more often than not — while a shared «de» broke Italian for
  everyone, every time.

- **The message catalogs moved to `engine/catalogs/`**, one module per
  language, discovered the way `localvoice/lang/` discovers its packs.
  `messages.py` is now the forty lines that *select* a catalog rather than the
  five hundred that *are* one; `messages.IT`/`.EN`/`.DE` and `msg()` are
  unchanged for every caller.

- **Each language pack's mood vocabulary moved next door**, to
  `localvoice/lang/moods_{it,en,de}.py`. Same reason and same size guard: the
  spoken vocabulary is a word list, not grammar, it is the half that grows, and
  it is the half `engine/moods.py` is meant to read from generated data one
  day. The packs re-export it, so the contract in `lang/base.py` is unchanged.

- **Spotify, through the LMS Spotty plugin.** «da spotify metti Comfortably
  Numb» now works the way «da tidal …» and «da qobuz …» do, the source selector
  lists it when the plugin is installed, and the Home Assistant blueprint
  accepts it too. **It needs Spotify Premium**: Spotty plays through Spotify
  Connect, which free accounts cannot use, and its login will not complete
  without one. This reverses a documented decision: the README said "No
  Spotify" because Spotify Lossless is not delivered to third-party Connect
  clients, so Spotty/librespot still gets lossy Ogg Vorbis 320 kbps. That is
  still true and still says TIDAL or Qobuz is the better source on a
  bit-perfect chain — it is just no longer a reason to refuse to reach a
  service you already pay for.

  **Spotty's feed is not shaped like the other two**, and the support is
  written to what it actually answers, read off a live LMS 9.0.3 on
  2026-08-28: there is no "Songs" category — the search node returns the
  category links with the matching tracks as their siblings — a track carries
  no url at all (it is the name of its single audio child, one level down), and
  title, artist and album arrive as one string, "T by A from B". The url is
  fetched for the track actually being played rather than for all twenty that
  were searched.

  **One behaviour is deliberately different from TIDAL and Qobuz.** Vivavoce
  normally falls back to "nothing matched, so trust the search engine's ranking
  and act on the top result". That is safe where an empty answer is possible —
  TIDAL and Qobuz return *nothing* for «zzzzqqqxyzzy» — and unsafe on Spotify,
  which answers every query with a full page of tracks, albums, artists and
  playlists. On Spotify the fallback is off for all four: if nothing matches,
  Vivavoce says so. Acting on something nobody asked for, silently, is the one
  failure this project is built to avoid, and a service whose search never says
  "no" would have introduced it — in four places, not one.

- **Vivavoce answers Home Assistant's voice assistant.** One blueprint,
  [`blueprints/vivavoce_assist.yaml`](blueprints/vivavoce_assist.yaml), and one
  `rest_command` block: say «metti Comfortably Numb dei Pink Floyd» to Assist —
  a voice satellite, the phone app, the dashboard — and the reply names the song
  that *actually started*, not the words the microphone thought it heard. The
  "which one did you mean?" list works too — «la 2» through «la 5», and the
  ordinals — and on a voice satellite it is meant to be asked out loud and
  waited for, which is the one branch no one here could test without a
  satellite to test it on. Setup is in
  [DEPLOY.md](DEPLOY.md#home-assistant-voice--talking-to-vivavoce-through-assist).

  It coexists by construction: Home Assistant tries sentence triggers before its
  own intents, so the blueprint only ever sees the music sentences it lists, and
  uninstalling is deleting one automation. Transport — pause, resume, next,
  volume — is deliberately **left to Home Assistant**, which already covers it
  in both languages and does it room-aware. Search is the opposite case:
  `HassMediaSearchAndPlay` starts the first result without asking, cannot filter
  by artist, and is missing from the Italian intent pack entirely.

### Removed

- **macOS riprende la parola chiave lato server.** Ritirando openWakeWord si
  era perso l'unico motore che su macOS si installava, e la spiegazione che ho
  scritto allora — «vosk non pubblica wheel per macOS» — era vera della 0.3.45
  e di nient'altro: le wheel `universal2` sono esistite **fino alla 0.3.44**, e
  la 0.3.45 le ha tolte per una regressione upstream aperta
  ([#1316](https://github.com/alphacep/vosk-api/issues/1316),
  [#2013](https://github.com/alphacep/vosk-api/issues/2013)). `pyproject.toml`
  chiede ora due versioni dietro marker d'ambiente: `>=0.3.45` ovunque,
  `>=0.3.44,!=0.3.45` su Darwin — l'esclusione e non un tappo, così una
  0.3.46 che ripari macOS viene presa da sola invece di restare fuori in
  silenzio. I marker e non un floor più basso, perché uv
  risolve **una** versione per tutte le piattaforme — con `>=0.3.44` e basta il
  lock avrebbe scelto comunque la 0.3.45, lasciando macOS senza niente da
  installare. Con i marker il lock porta due voci, e per Darwin l'unica wheel
  elencata è la `universal2`.

  Le due versioni sono state misurate fianco a fianco sulle stesse
  registrazioni prima di sceglierlo, perché «probabilmente uguale» non è un
  numero: stesso avviso di vocabolario su `fd 2` carattere per carattere,
  15/15 in stanza silenziosa, 15/17 sopra la musica, 0 falsi trigger su 40
  minuti di sala. La release vecchia oggi non costa niente — ma è un ponte, non
  una destinazione: se macOS non torna a monte, quelle macchine restano su una
  versione che non si muove più.

  In CI c'è ora una gamba macOS, perché «su macOS si installa» era
  un'inferenza da PyPI che niente verificava. Fa girare il **controllo del
  lessico** sulla versione che macOS risolve davvero: la prima stesura lo
  saltava dicendo che era «coperto su Linux», e non lo era — Linux gira la
  0.3.45, e la 0.3.44 è l'unica cosa che quella gamba debba provare.

  Cade con questo `wheels_unavailable_here()`, la funzione che spiegava dove
  vosk non si installa. Non le resta nessun membro — wheel per linux
  x86_64/aarch64/armv7l, win_amd64 e macOS universal2 — e una funzione che
  elenca un insieme vuoto è un commento travestito da codice.

- **openWakeWord è andato in pensione, e con lui il tetto a Python 3.11.**
  Stava lì come ripiego dopo l'arrivo del motore Vosk, ed era un ripiego che
  costava più di quanto rendesse. Sentiva soltanto le poche frasi inglesi per
  cui spedisce un modello, quindi «ascolto continuo senza beep» significava
  rinunciare alla frase scelta in casa; il suo pin esatto a
  `openwakeword==0.4.0` esisteva perché dalla 0.5.0 dipende in modo rigido da
  `tflite-runtime`, che non pubblica wheel oltre Python 3.11, e quel pin si
  trascinava dietro un job di CI inchiodato a quella versione; e i suoi modelli
  pre-addestrati sono **CC-BY-NC-SA** — non Apache-2.0 come questo repo ha
  sostenuto per mesi — dietro un livello a pagamento.

  Se ne vanno insieme a lui: il gruppo `wakeword` e il pin, la variante Docker
  `WAKEWORD=1`, il job `server wake word (py3.11, …)`, il flag
  `--wakeword-model`, `localvoice/pro/wakeword.py` e i suoi test. Il gruppo che
  resta non ha soffitto di versione — vosk spedisce wheel `py3-none-*` — e ha
  un wheel `armv7l`, quindi la tabella si è capovolta: sul Raspberry Pi a
  32 bit, l'unica macchina a cui questo repo diceva «nessuno dei due motori
  opzionali si installa qui», ora la parola chiave lato server si installa. È
  il riconoscimento vocale locale a restare a 64 bit.

  Il pannello delle impostazioni si semplifica di conseguenza. C'erano due
  suggerimenti perché c'erano due grammatiche — una frase libera in un fiato,
  una frase inglese fissa in due tempi — e il campo di testo spariva quando era
  attivo il motore che non poteva sentirlo. Ora il campo resta sempre, tutti e
  due i suggerimenti citano la stessa frase, e l'override che serviva a
  contraddirlo non c'è più.

  **Cosa si perde**, detto per intero: su macOS vosk non pubblica wheel, quindi
  lì il motore lato server non c'è più affatto. Il beep che questa funzione
  esiste per togliere è però un problema dei browser Android, che su un
  desktop macOS non si presenta: quelle macchine restano sul motore del
  browser, come prima, senza niente da rimpiangere.

## 0.4.0 — August 2026

### New

- **Vivavoce now says it is a machine.** A line under the microphone —
  «Assistente automatico: stai parlando con un software, non con una persona» —
  and, when the read-back voice or continuous listening is on, one sentence
  spoken at the start of a session. This is Article 50(1) of the EU AI Act,
  applicable since 2 August 2026 to any system that interacts directly with
  people, and it binds software already on the market. The Commission's
  guidelines open their list of examples with "AI-enabled voice assistants",
  and speech reaches this app through a neural model in every configuration —
  the browser's by default, Whisper on your own server with the Pro install —
  so the obligation is ours. The notice sits with the controls rather than in
  a menu, and nothing can switch it off: a disclosure reachable only from the
  settings is not one.

- **[`docs/ai-act.md`](docs/ai-act.md) — where the app stands under the AI Act,
  article by article.** The guidelines put the burden of that assessment on
  the provider, and the interesting half is the negatives: transcription is
  not synthetic content, so nothing needs marking; `engine/moods.py`
  classifies music and not the mood of the listener; nothing anywhere
  recognises *who* is speaking; and the regex-and-`difflib` router is not an
  AI system at all under the Commission's own definition. Households running
  Vivavoce at home carry no obligations of their own (art. 2(10)).

- **[`licenses/MODELS.md`](licenses/MODELS.md)** records which speech models
  the optional installs pull in, from where, and under which licence.
  Vivavoce ships no weights of its own.

### Changed

- **Kid-safe says why a song is refused, not how old you are.** «Questa canzone
  c'è, ma non è adatta alla tua età» claimed to know something the gate cannot
  know: nothing here recognises who is speaking. The decision is three facts —
  kid-safe is on, *this browser* has not typed the PIN in the last fifteen
  minutes, a blocklist term matched — and every one of them is about a device
  and a list. It now names the real reason, which is also the actionable one.

- **GET routes are now held to the Host allow-list.** Only `do_POST` consulted
  it, so the check added against DNS rebinding was protecting no readable
  route: under rebinding the attacker's page is same-origin with us and could
  read `/license`, `/players`, `/kidsafe` and `/nowplaying`. **If you reach
  Vivavoce through a DNS name of your own, put it in
  `VIVAVOCE_ALLOWED_HOSTS`** — such a setup now gets a 403 on the page itself
  where before the page loaded and only the commands failed. Nothing that
  worked stops working (POST always required the same list, so those installs
  could never issue a command), but the failure is louder and looks worse.

- **The container renews its TLS certificate on every boot** instead of
  generating one only when the files are missing. The server leaf now runs 800
  days rather than to a fixed date — Apple refuses any server certificate
  valid for longer — which turned "generate if absent" into a time bomb with
  nothing to defuse it. Only certificates our own CA signed are reissued, and
  the CA itself is reused, so nobody reinstalls anything on their phones. It
  does mean the container writes to your data directory on every start.

- **The README's privacy section matches the code again.** "Everything else
  never leaves your LAN" did not cover the artwork proxy, which for TIDAL and
  Qobuz fetches whatever CDN URL the plugin reports, nor the one-time Whisper
  model download, nor the machine's hostname, which rides along with a licence
  activation as its `instance_name`. `PRIVACY.md` said "nothing else is sent"
  about that same activation. All three are now stated where the claim is.

### Fixed

- **The five-attempt PIN gate allowed a great many more than five.**
  `verify_pin` read the counter, spent ~100 ms in PBKDF2, and only then
  incremented it, with no lock held across the two — so every request that
  arrived before the first write saw zero attempts. The server runs one thread
  per connection and allows 128 of them.

- **A room command no longer aims everybody else's music.** «metti Time in
  cucina» retargeted the turn by swapping `self.lms` and restoring it in a
  `finally` — correct for one turn at a time, and this `Router` is not one turn
  at a time: `http_api` caches one per conversation and the server is threaded.

- **`kidsafe.json` had two writers and no shared lock.** The PIN half and the
  blocklist half each read the whole file and wrote the whole file back, so
  whichever read first wrote last and silently dropped the other's changes. A
  save that fails is now reported instead of swallowed.

- **Switching continuous listening off takes the command capture with it.**
  Only the wake stream was stopped; the capture it had opened ran to its
  30-second cap, transcribed, and — with auto-send on, which wake mode implies
  — answered whatever the room happened to be saying, long after the panel had
  gone dark and said "tap the microphone".

- **The whole continuous-listening block is put away when the trial ends**, not
  just its hint paragraph: engine choice, keyword field and both hints used to
  stay on screen under a checkbox that had just been disabled.

- **The wake word picks the entry that contains it**, rather than any entry
  merely longer than the stray interim result the fallback was holding — and a
  stray is routinely longer than the command it interrupts.

- **A server-side wake word that cannot resolve its model no longer reports
  itself as available.** `--wakeword-model hey_vivavoce` printed "attiva" and
  then detected nothing, because the check only asked whether `openwakeword`
  imports.

- **An expired install is no longer told at every boot that it has fourteen
  fresh trial days.**

- **`https: false` is honoured in the Home Assistant app.** The add-on reads
  its options with `jq -r '.[$k] // empty'`, and `//` falls through on `false`
  as readily as on a missing key — `https` being the only boolean option we
  expose.

- **The Docker healthcheck reads the same variable names the entrypoint still
  answers to.** A container still setting `SQUEEZESAY_HTTPS=0` served plain
  HTTP correctly and was reported unhealthy for it.

- **The service worker no longer caches an error page as a version of the
  app.** A 403, 404 or 500 could land under `/` or under a module's key and
  replace what the install had put there.

- **The seek bar survives losing the track under a finger.** The five-second
  poll, a `visibilitychange` or a failed fetch could drop the now-playing state
  mid-drag, and the next pointer event threw.

- **A blank alternative is not an alternative.** `alternatives: [""]` on
  `/api/v1/command` is a `str`, passed the type check, and became a one-item
  list that replaced the text instead of refining it.

- **A decade is no longer read out in a foreign voice.** The year went into the
  list of foreign names in the sentence, and the language guesser has nothing
  to go on in "1985", so «Ho messo qualcosa del 1985» broke mid-sentence into
  an English voice.

- **The systemd unit's startup lines reach `journalctl`.** No `-u`, so under
  systemd — where stdout is a pipe — Python buffered the server's ~700 bytes of
  startup diagnostics in 4 KiB blocks and showed none of it. **Existing
  installs need to re-copy `deploy/vivavoce.service` and `daemon-reload`** for
  this to take effect.

### Internal

- **`mic.js` outgrew the repo's own 400-line ceiling** during the wake-mode
  work; the local-recognition engine now lives in
  `localvoice/static/js/localasr.js`, which is in the service worker's shell.
  `VERSION` went to `vivavoce-v11`, so installed PWAs pick the new module up on
  activation.

- **`tests/test_ai_act_disclosure.py`** pins what a refactor could quietly
  undo: that the notice exists, sits in the interaction area, cannot be
  switched off by markup, stylesheet or script, exists in both languages, and
  is still wired to the start of listening. The wording is deliberately not
  asserted — it should stay free to improve.

- **A review pass over this release's own commits** closed five findings, four
  of them regressions the work had introduced itself — among them
  `tools/make_cert.py` truncating `key.pem` in place.

- **`RELEASING.md` step 6 expected four entries from `ls /app`** where the
  add-on Dockerfile copies five.

## 0.3.0 — August 2026

### Fixed

- **An apostrophe no longer hides a blocked name from kid-safe.** Text is
  normalised before the blocklist is checked, and that normalisation deletes
  apostrophes — deliberately, because the recogniser writes «dont stop me now»
  and the title is *Don't Stop Me Now*. Deleting also welds the character's
  neighbours into a single word, and a blocked term then has no boundary left
  to match on: a list holding *Eminem* stopped seeing "Eminem's Greatest Hits",
  one holding *Estasi* stopped seeing "L'Estasi dell'Oro". Italian elision —
  l', dell', un', sull' — put a blocked name one article away from being
  unreachable, and albums were the worst of it, because the title is the only
  field a streaming result carries a name in. Both spellings are now checked,
  so the recogniser's version and the elided one both match, and a blocked
  «ass» still does not match «bassista».

- **A song whose title contains «di», «della» or «by» plays again.** The parser
  reads the last connector in a request as the boundary between title and
  artist, which is what makes «Stand By Me by Ben E. King» find the right song
  — and it invented an artist for every title that merely contains one:
  «Cuore di Vetro» became *Cuore* by *Vetro*, «Notte Prima degli Esami» became
  *Notte Prima* by *Esami*. That used to cost nothing, until the app learned to
  say so when a named artist is nowhere in the results; the two together turned
  «metti Cuore di Vetro» into «Non ho trovato Cuore di Vetro» with the right
  track sitting first in the list, and spent the recogniser's next
  transcription on it too. Nine of nineteen real titles tried failed this way,
  most of them Italian. A request that matches a title whole, connector
  included, is now taken as the title it is. «Yesterday di Vasco Rossi» still
  refuses when only The Beatles are in the results, and still finds Vasco's
  edition when it is there.

  Titles that *open* with a connector were losing their first word for a
  related reason — «By the Way» searched for "the Way" — and no longer do.

- **A refusal no longer reports itself as a success — and no longer gets
  retried past.** Every reply carries a flag saying whether it acted on your
  request; for some replies that flag was not set but *guessed*, from whether
  the sentence began with «Non ». Plenty of refusals do not. «Per farlo in
  Cucina serve Pro» is one, and it was being handed to callers of
  `POST /api/v1/command` marked as a success, so a Home Assistant automation
  branching on it took the wrong branch.

  Fixing that flag uncovered the worse half. The app tries several of the
  recogniser's transcriptions in turn, stopping at the first that works — and
  a refusal now looked like something to try again. So «metti Beatles in
  salotto» on the free tier was refused, and then the second-best
  transcription, «metti Beatles», carried no room name, sailed past the very
  refusal that had just stopped it, and started the music in whichever room
  the selector pointed at. You never heard why. Kid-safe had the same hole and
  had had it longer: a blocked singer could be asked for repeatedly until one
  spelling slipped through.

  Refusals about *who is asking* — no Pro, not the parent, not for this
  listener — now end the turn, because no re-transcription of your words buys
  a license. Refusals about the *words* are still retried, which is the whole
  reason that machinery exists: «metti sfigati» becoming «metti Audioslave» on
  the second attempt still works exactly as before.

- **Blocklist replies no longer claim a room they do not have.** «blocca
  Eminem in salotto» answered «Ok, ho bloccato Eminem in Salotto», which
  describes a per-room blocked-songs list that does not exist — the list is
  the whole house. The read-out was worse: «Brani bloccati: Eminem in Salotto»
  reads as though «Eminem in Salotto» were the blocked term.

- **A player named after a word of a song no longer swallows the song.** If one
  of your players is called «America» and your library has *Breakfast in
  America*, «metti breakfast in america» used to be heard as a command for that
  room — and on an installation without Pro that meant an answer about Pro and
  no music at all: a record you own, served with an advertisement. Same for a
  player called «Bianco» and *Notte in bianco*, or «Paradise» and *Lost in
  Paradise*.

  A room name was only ever a *guess* about what the words meant, and it was
  being spent as if it were a fact. Both readings of the sentence — with the
  room and without it — are now looked up in your local library, and the one
  the library actually recognises wins. «breakfast in america» is the name of a
  record and «breakfast» merely resembles one, so the record plays; «bollicine
  in cucina» is the other way round, so it stays a room command and behaves
  exactly as before. A tie keeps the room, which is the safe direction: being
  told no costs you a turn, while music starting in the wrong room costs you a
  trip to go and stop it.

  The same reading applies with or without Pro, deliberately — which record
  your words name is not something a license should have an opinion about. And
  when Pro is active and a room you said out loud gets overruled this way, the
  answer says so («… — l'ho preso come titolo, quindi suona qui»), because a
  room that simply vanishes from the reply is a wrong guess you cannot see.
  «pausa in cucina» and «in cucina metti X» are untouched and do not even ask
  the library: there is no title in either of them to weigh.

  Three things this does not do. It needs a **local** library to consult, so an
  installation that only streams still gets the old answer. When your library
  holds *both* readings — a track called *Notte* and one called *Notte in
  bianco*, with a player called «Bianco» — the sentence really is ambiguous,
  and the room keeps it. And a title that resembles the whole sentence wins
  even when you meant the room: if you own an album called *Musica in Cucina*,
  «metti musica in cucina» plays it. With Pro the answer tells you that is what
  happened, so the correction is one sentence away.

### New

- **A documented API for other programs: `POST /api/v1/command`.** Vivavoce's
  command endpoint was always reachable — it is how the page itself works —
  but it was the web app talking to itself, free to change shape with the page
  it serves. It is now a versioned contract with `docs/api.md` behind it, so a
  Home Assistant blueprint, a script or an automation can send a sentence and
  get a structured answer back without reading the source to find out what the
  fields mean.

  Two things the contract adds. **`needs_choice`** says outright that the
  answer asked a question — «Ne ho diversi per Love. 1: … 2: … Quale metto?» —
  instead of leaving a caller to infer it from a list being non-empty.
  **`conversation_id`** names the session that the numbered list belongs to,
  and `docs/api.md` writes down how long it lasts (five minutes) and what
  happens when it runs out; the old field name `client` still works. The error
  branch was also brought in line: the reply used to drop `choices` when
  something went wrong, which is the worst moment for a field to vanish, and
  now every answer carries every field.

  `POST /command` keeps working, unversioned, answering exactly the same
  thing — nothing that already calls it has to move. The web app itself now
  goes through `/api/v1/command`, which is the only honest way to know the
  contract works. There is deliberately **no `room` field** yet, and
  `docs/api.md` says why rather than leaving it to be guessed at.

- **Vague requests now play something, and say what.** «metti qualcosa di
  rilassante», «musica per cena», «metti un po' di jazz» / "play something
  relaxing", "play some music for dinner" used to be searched for as if they
  were song titles, and of course nothing was ever called that. They now
  resolve through your library's own genres first — real music you own — and
  fall back to the streaming service's curated playlists only when the library
  has nothing to offer; asking for your own library keeps the answer local.
  The load asks LMS for a random album order, so a mood does not open on the
  same track every evening — it is the album order that is randomised, not the
  tracks inside an album, and it is scoped to that one request: your player's
  own shuffle setting is never touched.

  It also answers the axes your library already tags: **a decade** («metti
  musica anni ottanta» / "play some eighties music" — one year out of it, said
  out loud, and «un'altra» gives another year of the same decade), **Christmas
  music**, **instrumental** / "without words", and **summery**. A decade the
  library has nothing from says so rather than playing the nearest thing.

  Every reply reads back what it started («Ho messo un po' di Ambient») and
  invites «un'altra» / "another one", which picks something different until
  the ideas run out and it says so. Choosing is only allowed here because
  nothing was named: a request that names a song, an album or an artist is
  untouched — «metti Bollicine di Vasco» behaves exactly as before, and so
  does a song whose title happens to be a mood word. Still deterministic,
  still no model anywhere: a lookup table and your library's metadata.

- **The container image is published**, so "Docker — one command" is finally
  one command: `docker run … ghcr.io/lucabon/vivavoce:latest`, no clone and no
  build. Every release tag publishes for **amd64 and arm64** as `:X.Y.Z`,
  `:X.Y` and `:latest`. Building from a checkout is unchanged — the compose
  file in the repo still builds from source, with the published image as a
  commented alternative — and a 32-bit Raspberry Pi still builds its own, which
  DEPLOY.md now says instead of implying otherwise.

- **Guided certificate setup.** The mic needs HTTPS, so the browser's "your
  connection is not private" warning stood exactly in front of the feature
  people pay for. The *"Installa come app"* panel now recognises that state and
  opens by itself, shows the two steps for **your** device only (Android,
  iPhone/iPad, Windows, macOS, Linux — the others are one tap away for when you
  are setting up a phone from a laptop), and checks by itself that it worked.
  The check is not a guess: a browser refuses to register a service worker on
  an untrusted certificate, so a registration that succeeds *is* the proof the
  CA is installed. It also knows the cases where there is nothing to do —
  you are on the server machine, the server serves plain HTTP, or it uses a
  certificate of its own — and asks for nothing in each. DEPLOY.md additionally
  documents the ACME/DNS-01 route for households that own a domain and would
  rather install nothing on any device.

- **14 days of full Pro on every install**, microphone included — no key, no
  card, no account, and no network call: the window is one timestamp in the
  data directory, opened the first time the server starts. Because it lives
  server-side it also unlocks the features enforced there (local speech
  recognition, server-side wake word), and clearing the browser's storage does
  not re-arm it. When it ends, typed commands keep working exactly as before —
  nothing breaks, nothing is deleted. The settings panel says how many days
  are left rather than claiming a license nobody bought, and after a command
  you typed, the page points out — at most once per session, and never in the
  first two days — that you could have simply said it.
- **Queue management** (free): «aggiungi X alla coda» / "add X to the queue"
  queues a song at the end; «metti X dopo questa» / "play X next" queues it
  right after the current track; «svuota la coda» / "clear the queue"; «cosa
  c'è in coda» / "what's in the queue" reads back what's coming up. Reuses
  the existing title/artist parsing and "did you mean" disambiguation — a
  queue command that opens a numbered list queues (not plays) whichever one
  you pick — and works with multi-room («aggiungi X alla coda in cucina»).
- **Favorites & radio** (free): «riproduci i preferiti» / "play my favorites"
  plays a saved LMS favorite; «metti la radio X» / "play the radio X"
  searches your favorites for a matching station name. Built on the LMS core
  Favorites API (not a specific radio plugin), so it works with however you
  already saved your stations — TuneIn, a plugin, or a raw stream URL.
- **Server-side wake word** (Pro, optional install — `uv sync --group
  wakeword`, its own group, see DEPLOY.md): an alternative to the browser's
  continuous-listening mode that eliminates the Android beep — the single
  most-cited launch complaint — by streaming mic audio to the server, which
  runs openWakeWord (CPU, no GPU) instead of restarting Web Speech every few
  seconds. Trade-off, upfront: only a fixed English phrase ("hey jarvis")
  today, not the free-text wake word — offered as an *additional* choice
  next to it, not a replacement. A new settings switch appears once the
  server reports the engine installed.
- **"Report a misunderstood phrase"** (free, privacy-first): when a command
  isn't understood, the reply offers a button that saves the report on your
  device and opens a pre-filled GitHub issue (phrase, language, source,
  version) for you to review and submit. Nothing is ever sent by the app
  itself — see PRIVACY.md.

### Changed

- **Asking for another room without Pro now says which room it heard**, and how
  to get the music anyway: «Per farlo in Cucina serve Pro. Dillo senza la
  stanza e lo faccio qui.» It used to answer with the same generic sentence
  that answers kid-safe, which told you neither. Naming the room is the useful
  part — a room name is only ever a guess about what the words meant, so
  hearing it back is what lets you see a wrong guess. If you have a player
  called *America*, «metti breakfast in america» is read as a room command, and
  now you can tell at once why a song you own was answered with a Pro notice
  instead of music. That it is read as a room command at all is a separate
  problem, still open.

- **The Docker data volume is now `vivavoce-data`**, not `squeezesay-data`. It
  holds the TLS certificate, the licence, the trial window and the kid-safe
  blocklist, so a `docker compose pull && up -d` that silently starts on an
  empty one looks like the app forgot everything it knew. Nothing is deleted:
  the old volume is still there, and `DEPLOY.md` has the two commands that copy
  it across. Only Docker is affected — the Home Assistant app keeps using the
  Supervisor's own storage, which never had the old name.

### Fixed

- **`/command`, `/kidsafe`, `/player` and `/license` no longer drop the
  connection on a non-object JSON body** (`null`, a bare number, a string, a
  list): `json.loads` accepted it without raising, and the unguarded
  `.get(...)` that followed crashed with an uncaught `AttributeError`,
  contradicting each endpoint's own "never a 5xx" design — on `/license`,
  the one endpoint that handles a paid key. Pre-existing (found during a
  post-phase review of the Fase 1 diff, not introduced by it); now covered
  by tests on all four routes.

### Internal

- **The browser suite can no longer skip in silence.** `playwright install`
  exits 0 when it fails — it prints "Failed to install browsers" and returns
  success — so a broken install left a green CI job in which every browser test
  had skipped, which is exactly what had been happening locally. CI now sets
  `VIVAVOCE_REQUIRE_BROWSER=1`, under which those skips become failures, proves
  a browser really launches instead of trusting the installer's exit code, and
  falls back to `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE` on platforms Playwright
  does not recognise yet (Ubuntu 26.04 already refuses; `ubuntu-latest` will
  get there). Three packaging tests keep CI from quietly dropping any of it.
- **Frontend split**: the 1.700-line `index.html` is now a markup shell plus
  native ES modules (`localvoice/static/js/`) and a real stylesheet — no
  bundler, no new dependencies. The installed PWA refetches the shell once.
- **Browser end-to-end tests**: seven Playwright flows (page load, command
  round trip, "did you mean" tap, license activation, now-playing, the report
  button, settings persistence) run headless in CI against the same fake-LMS
  stack as the rest of the suite.
- **Plug-in languages**: the router's IT/EN patterns moved into per-language
  packs (`localvoice/lang/`); adding a language is now one file plus its
  messages and tests — groundwork for German.
- **Server split**: `server.py` (startup/CLI) now stands apart from
  `http_api.py` (routes), `staticfiles.py` (assets) and `tls.py`;
  `python -m localvoice` works as a second entry point.
- **The Home Assistant app is a declared channel now**, not something that
  merely exists: it has the icon and logo the store requires, and the changelog it recommends
  (`ha-addon/`, artwork generated by `tools/make_icons.py`), and the docs
  follow Home Assistant 2026.2, which renamed *add-ons* to *apps* in the
  interface — menu paths name the new label and the old one, since nothing in
  the file names or config schema changed. `DEPLOY.md` also stopped
  recommending `:0.3.0`, a tag that was never released; a new packaging test
  checks every version the install docs quote against `pyproject.toml`, which
  is how it drifted unnoticed.

## 0.2.0 — August 2026

### SqueezeSay is now Vivavoce

The project is renamed **Vivavoce** (Italian for "hands-free / speakerphone").
"Squeeze-" echoed the Logitech Squeezebox trademark — the same reason the LMS
project itself renamed to Lyrion. What this means for existing installs:

| You use | What to do |
|---|---|
| Docker compose | `docker compose pull && docker compose up -d`. The data volume keeps its old internal name on purpose: your certificate (and license, see below) survive. Container/service are now called `vivavoce`. |
| Env variables | New names are `VIVAVOCE_*`. The old `SQUEEZESAY_*` names keep working **for this release only**, printing a deprecation note. |
| Home Assistant add-on | The add-on slug changed, so the Supervisor sees a **new add-on**: uninstall the old "SqueezeSay" one, add the repo again (`https://github.com/LucaBon/vivavoce`) and install **Vivavoce**. The old `/data` is not migrated — you'll re-accept the certificate once and re-enter your license key (this consumes one of your 5 activations). |
| Windows autostart | Re-run `tools/install_autostart.ps1`; `tools/uninstall_autostart.ps1` cleans up both the old and the new task/firewall names. |
| systemd | The unit is now `deploy/vivavoce.service`. |
| Installed PWA | The app updates itself on the next online open; the icon label may show the old name until you reinstall it (cosmetic). |
| Wake word | The default is now "vivavoce"; if you had saved a custom wake word (including "impianto"), it is preserved. |

### New

- **Now-playing panel** (free): artwork, title/artist/album, play/pause lamp,
  transport buttons, a draggable seek bar and a **volume slider**, at the top
  of the page.
- **Multi-room** (Pro, `localvoice/pro/multiroom.py`): a "Dove suona la
  musica" selector appears in settings when the LMS has more than one player,
  and any command can target a room on the fly: «metti Time **in cucina**»,
  «pausa in salotto» ("play … in the kitchen"). A follow-up «metti la 2»
  keeps playing in that room. Enforced server-side, like kid-safe.
- **Sleep timer** (free): «spegni tra 30 minuti», «stop in half an hour»,
  «annulla il timer» — the LMS native sleep timer, armed by voice.
- **Local speech recognition** (Pro, `localvoice/pro/asr.py`, optional
  install): the mic can transcribe on *your* server with **faster-whisper**
  instead of the browser's cloud engine — the audio never leaves the LAN,
  closing the one non-local step in the privacy story. Enable with
  `uv sync --group asr` (or the Docker `--build-arg ASR=1` image) and flip
  «riconoscimento vocale locale» in settings; Web Speech remains the default
  and the automatic fallback. Model configurable with `--asr-model` /
  `VIVAVOCE_ASR_MODEL`, cached in the data directory; the default is
  RAM-aware — `small` on ~4 GB+ machines, off below that (the smaller models
  mangle English song titles; an explicit `--asr-model` always wins). As a
  bonus, the mic now also works on browsers without Web Speech (Firefox).
- **LMS status lamp** (free): the header LED turns red — with a clear message —
  when the music server is unreachable, instead of failing silently.
- **Vivavoce Pro** — one-time license (11,90 €; launch price 8,90 €) that
  unlocks the microphone, the wake word, the multilingual read-back voices and
  kid-safe. Activation is once-online, then cached: offline never disables it.
  The core stays free (text commands, all search/playback, transport) and is
  now formally **AGPL-3.0** (the repo previously had no license).
- **Kid-safe on the web app** (Pro): PIN-protected blocklist, enforced
  server-side for every device on the LAN, editable by voice («blocca …»,
  «sblocca …», «quali brani sono bloccati») or from settings.
- **Auto-discovery from inside Docker bridge/NAT** (free): when the UDP
  broadcast can't leave the container (Docker Desktop on Windows/Mac, bridge
  networks), the server now falls back to a **unicast sweep** of the LAN — LMS
  answers the same discovery request sent host-by-host — and remembers the
  server in the data volume, so restarts skip discovery entirely.
  `docker compose up` is zero-config everywhere, not just with host networking.

### Removed

- **The Alexa skill.** It required an always-on HTTPS tunnel and a developer
  account per household — unmaintainable, and the web app does the job
  without any cloud. The engine lives on under `engine/` (was `lambda/`).

### Internal

- **CI** (GitHub Actions): every push and pull request runs the test suite on
  Python 3.9–3.14 plus a Windows job (the `%APPDATA%` data-directory branch a
  Linux-only matrix never executes), byte-compiles every module — `tools/` is
  imported by no test, so a syntax error there used to reach the user — and
  builds the Docker image, which is the only thing that catches a `COPY`
  pointing at a moved file.
- **Integration tests** (489 → 531): the PWA shell (`sw.js` pre-caches its
  asset list atomically, so a single 404 silently stopped the app being
  installable), the `/command` path end-to-end from HTTP down to the commands
  the LMS actually receives, and the release descriptors — the add-on version
  must match `pyproject.toml`, and every Dockerfile `COPY` source must exist.
