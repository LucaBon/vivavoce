# Vivavoce e Home Assistant — spike di integrazione

> Documento di ricerca e design per **T3.1**. Stato: **proposta**, non ancora
> decisa. Le date di verifica sono nel testo perché in quest'area cambia tutto
> ogni due mesi e una frase senza data qui è rumore.
>
> Verifiche fatte per questo documento: **2026-08-26**. Dove riporto qualcosa
> che era già stato verificato il 2026-08-25 e non ho ricontrollato, lo dico.
> Dove non sono riuscito a verificare, lo dico anche quello — sta tutto nella
> [§1.4](#14-cosa-non-sono-riuscito-a-verificare), e va letto prima di decidere.

---

## 1. Stato dei fatti

### 1.1 L'ecosistema, per come è fatto davvero

**Music Assistant non è un'integrazione di Home Assistant: è un server.**
Confermato il 2026-08-26 sulla pagina di installazione: si installa come *app*
di Home Assistant (solo su HAOS) oppure come container Docker; l'integrazione
Home Assistant è un passo **successivo e opzionale**, e serve a esporre i
player di MA come entità `media_player` più sei azioni. Il progetto è della
Open Home Foundation ed è **Apache-2.0** (verificato il 2026-08-26 via API
GitHub su `music-assistant/server`, 2.979 stelle, ultimo push lo stesso
giorno). Anche Home Assistant core è Apache-2.0 (verificato allo stesso modo).
Questo secondo dato non è un dettaglio burocratico: decide da solo due delle
quattro opzioni più sotto.

**L'intent *Search and Play* esiste da HA 2025.6 ed è nel core**, non in Music
Assistant. Il codice sta in `homeassistant/components/media_player/intent.py`,
`class MediaSearchAndPlayHandler` — l'ho letto sul branch `dev` il 2026-08-26.
Vale la pena citarlo alla lettera, perché la riga più importante è la
docstring che l'autore ha scritto senza giri di parole:

```python
description = "Searches for media and plays the first result"
...
slot_schema = {
    vol.Required("search_query"): cv.string,
    vol.Optional("media_class"): vol.In([cls.value for cls in MediaClass]),
    ...
}
...
# 2. Play Media (first result)
first_result = results[0]
```

Non c'è nessuno slot `artist`. Non c'è nessun ramo che, davanti a più
risultati plausibili, si fermi a chiedere. `results[0]` è tutta la strategia di
scelta, ed è **una decisione di design dichiarata**, non un difetto che
qualcuno chiuderà in silenzio: la roadmap lo aveva intuito il 2026-08-25 dalle
docs, il sorgente lo conferma. Se un giorno cambierà, cambierà con un annuncio.

**Precisazione che la roadmap non aveva: *Search and Play* non è specifico di
Music Assistant.** L'handler non conosce MA. Cerca il target fra le entità
`media_player` che dichiarano `MediaPlayerEntityFeature.SEARCH_MEDIA` e
`PLAY_MEDIA`, poi chiama i servizi generici `media_player.search_media` e
`media_player.play_media`. Qualunque integrazione che implementi
`async_search_media` ci finisce dentro gratis. È la notizia buona e la notizia
cattiva insieme, e la spiego in §1.2.

**L'italiano non è coperto.** Verificato il 2026-08-26 elencando via API i
contenuti di `OHF-Voice/intents`: le lingue che hanno una cartella
`sentences/<lang>/HassMediaSearchAndPlay` sono diciannove —
`bg ca cs cy de el en es fr ga hu nl pt-BR ro sk sr sr-Latn th zh-TW` — e
`it` **non c'è**. La cartella italiana esiste e contiene trentatré intent
(timer, luci, clima, `HassMediaPause`, `HassMediaNext`…), ma né
`HassMediaSearchAndPlay` né `HassMediaPlayerMute`/`Unmute`. In pratica: **oggi
un utente Assist che parla italiano non ha nessuna frase predefinita per far
partire la musica.** Questo è il singolo fatto più favorevole a Vivavoce in
tutto il documento, ed è anche il più fragile: è una PR di traduzione, non
un'architettura. Chiunque può chiuderlo in un pomeriggio.

### 1.2 Il concorrente vero non è Music Assistant

Questa è la scoperta che sposta l'analisi, e non era nella nota della roadmap.

**L'integrazione `squeezebox` (Lyrion Music Server) è già nel core di Home
Assistant e dichiara già `SEARCH_MEDIA`.** Verificato il 2026-08-26 sul
sorgente `homeassistant/components/squeezebox/media_player.py`: la feature è
nella maschera alla riga 227, `async_search_media` è implementata alla riga
659, `quality_scale: silver`, tre codeowner. Conseguenza diretta: ***Search and
Play* funziona già oggi su un impianto LMS, senza Music Assistant di mezzo,
sulla stessa identica macchina su cui gira Vivavoce.** Il confronto non è più
"Vivavoce contro un server che l'utente potrebbe installare"; è "Vivavoce
contro qualcosa che l'utente ha già".

Ma è esattamente qui che il divario diventa *misurabile* invece che
argomentato, perché quell'implementazione ha tre limiti che si leggono nel
codice:

1. **Cerca solo nella libreria locale.** Costruisce la lista dei tipi da
   `["albums", "tracks", "artists", "genres", "playlists"]` e scarta
   esplicitamente `apps`/`app`/`radios`/`radio`. Su LMS, TIDAL e Qobuz sono
   *app*. Quindi **«play Comfortably Numb» non troverà mai un brano in
   streaming**: se non ce l'hai in libreria, non esiste. Vivavoce cerca in
   locale, TIDAL e Qobuz.
2. **Non filtra per artista**, perché non ha dove metterlo: lo slot non esiste
   a monte, nell'intent.
3. **L'ordine dei risultati è la concatenazione dei tipi in quell'ordine.**
   Gli album vengono prima delle tracce. Combinato con `results[0]`
   dell'intent, significa che «play Comfortably Numb» su una libreria che
   contiene un album con quella parola nel titolo fa partire **l'album**, non
   il brano — in silenzio, senza dire che ha scelto.

Non ho un impianto HA + LMS su cui provarlo, quindi lo dichiaro per quello che
è: **una lettura del sorgente, non una prova sul campo.** È la prima cosa da
verificare empiricamente prima di scrivere qualunque riga di T3.3, ed è
un'ora di lavoro con un HA di prova.

### 1.3 Cosa ho letto che nessuno aveva ancora letto

**`github.com/music-assistant/voice-support`** (letto il 2026-08-26;
Apache-2.0, 319 stelle, ultimo push 2026-08-24). Contiene **tre** blueprint,
non uno:

- `local-assist-blueprint/` — frasi custom, zero LLM, nove lingue
  (`de en es fi hu it nl pt-br sk`);
- `llm-enhanced-local-assist-blueprint/` — le stesse frasi più un LLM (OpenAI
  o Google) per le formulazioni libere, tre lingue;
- `llm-script-blueprint/` — uno script esposto come *tool* a un agente LLM.

Ho scaricato e letto per intero **il blueprint italiano** (210 righe). Va detto
chiaramente perché contraddice in parte la nota della roadmap: **l'italiano
c'è, e copre l'artista.** Il trigger album è

```yaml
"(riproduci|ascolta) [(l'|il|la) ](album|ep|disco|compilation|singolo) {media_name}
 [(di|dell'|della|dei|degli) [(artista|band|gruppo) ]{artist}]
 [(in|su|usando) [(il|la) ]{area_or_player_name}][ (con|usando) {radio_mode}]"
```

cioè filtro per artista, targeting per stanza e *radio mode* — le tre cose che
*Search and Play* non fa. Il meccanismo è un'automazione con `trigger:
conversation`, che chiama `music_assistant.play_media` passando `media_id`,
`media_type`, `artist`, `radio_mode`, e chiude con `set_conversation_response`.

**Il limite del blueprint è però esattamente il punto in cui vive Vivavoce, e
si legge in tre righe di YAML:**

```yaml
- alias: Send media to selected Music Assistant Player
  action: music_assistant.play_media
  data: '{{ dict(action_data.items() | selectattr(''1'')) }}'
- alias: Send back the response
  set_conversation_response: '{{ trigger.slots.media_name }} in riproduzione su {{ mass_player_name }}'
```

È **fire-and-forget**. Non guarda cosa è stato trovato, non sa se è partito
qualcosa, e annuncia *«X in riproduzione»* con la stringa che ha sentito
l'utente — anche se MA ha fatto partire un'altra cosa, anche se non ha fatto
partire niente. Il fallimento silenzioso non è un rischio residuo di quel
design: è il comportamento normale. E la sintassi va imparata a memoria: la
frase **deve** iniziare con `riproduci`/`ascolta` **seguito dal tipo**
(`album`, `traccia`, `artista`, `playlist`, `radio`). «Metti Comfortably Numb
dei Pink Floyd» — la frase con cui si apre il README di Vivavoce — **non
matcha nessuno dei cinque trigger**, perché manca la parola `traccia`.

**`music_assistant.search` esiste, restituisce dati, e accetta l'artista.**
Verificato il 2026-08-26 su `homeassistant/components/music_assistant/services.yaml`:
campi `name` (obbligatorio), `media_type` (multiplo), **`artist`**, **`album`**,
e `search_options` con `limit` (default 5, max 100) e `library_only`. Quindi
la formulazione «Music Assistant non sa filtrare per artista» è **falsa a
livello di API**. Quello che manca in MA non è il filtro: è lo strato che
*sceglie fra i risultati e chiede quando non è sicuro*. Questa correzione conta,
perché sposta il valore difendibile di Vivavoce da "sappiamo cercare meglio" a
"sappiamo **decidere** meglio, e sappiamo quando non decidere". La seconda è
una posizione più onesta e, per come sono fatti gli ecosistemi, più difendibile.

**I sentence trigger vengono valutati *prima* degli intent predefiniti.**
Questo è il fatto tecnico su cui poggia tutta la raccomandazione, e l'ho
verificato sul sorgente il 2026-08-26 —
`homeassistant/components/conversation/default_agent.py`,
`DefaultAgent._async_handle_message`:

```python
# Check if a trigger matched
if trigger_result := await self.async_recognize_sentence_trigger(user_input):
    ...
if response is None:
    # Match intents
    intent_result = await self.async_recognize_intent(user_input)
```

Prima i trigger dell'utente, e **solo se nessuno matcha** gli intent built-in.
Non è una precedenza configurabile né un caso fortunato: è l'ordine del
metodo. Significa che una frase Vivavoce e *Search and Play* possono vivere
nello stesso Assist senza che nessuno dei due vada disattivato.

**Ma la stessa funzione dice anche che un blueprint non può chiedere «quale
intendi?».** Il `ConversationResult` costruito per un trigger è
`ConversationResult(response=response, conversation_id=chat_log.conversation_id)`:
`continue_conversation` non viene mai impostato, quindi resta `False` e il
turno si chiude. Un'automazione può *rispondere*, non può *tenere aperta la
conversazione*. C'è una via d'uscita — `assist_satellite.ask_question`,
introdotta in HA 2025.7 (dal blog di rilascio; la pagina dell'azione non
riporta la versione), che fa una domanda e restituisce `{id, sentence, slots}`
con match a template — ma funziona **solo su entità `assist_satellite`**:
Voice PE, satelliti ESPHome/Wyoming. Chi parla ad Assist dall'app companion o
dalla dashboard non ha un `assist_satellite` e resta scoperto.

**Il Provider MCP di MA 2.9 è reale, ufficiale e dichiarato sperimentale.** È
il plugin *FastMCP Server* (pagina letta il 2026-08-26): single-instance, si
installa da Settings → Plugins, parla **HTTP** riusando il webserver di MA su
un percorso configurabile (`/mcp/v1` di default), richiede un token
long-lived, ed espone libreria, ricerca, riproduzione, code e playlist come
tool MCP. La documentazione avverte per iscritto: *«This plugin is still in an
early stage of development. Bugs may occur»* e *«the plugin is experimental and
the Model Context Protocol itself is still evolving, so behaviour may change
between Music Assistant releases»*. Nota di attribuzione: i "46 tool in sei
categorie" che si trovano in giro nei risultati di ricerca vengono da server
MCP **di terze parti** (`jakekeeys`, `devjourney`, `davidpadbury`), non dal
plugin ufficiale; non ho verificato il conteggio dei tool di quello ufficiale.
Direzione del flusso, che è ciò che conta qui: MCP serve a far **guidare** MA
da un agente LLM esterno. **Non è un punto in cui inserire un motore di
matching** — è l'opposto, è MA che si offre come strumento a qualcun altro.
Per Vivavoce sarebbe rilevante solo il giorno in cui l'engine diventasse un
agente LLM, che è precisamente la strada che il posizionamento esclude.

**`music-assistant/intents`** — repository separato con
`custom_sentences/en/`: **fermo dal 2024-11-24, due stelle, solo inglese.** Un
esperimento superato dai blueprint. Lo cito solo perché chi cerca finisce lì e
crede che sia il canale ufficiale.

**«Add-on» adesso si chiama «App».** Home Assistant 2026.2 (febbraio 2026) ha
rinominato Add-ons in Apps in tutta l'interfaccia e nello store; Supervisor
2026.05.1 e 2026.06.0 hanno completato il rename in file, import e schemi di
configurazione. **I nomi dei file non sono cambiati**: il repository di
esempio ufficiale (`home-assistant/addons-example`, controllato il 2026-08-26,
ultimo push 2026-07-30) ha ancora `repository.yaml` alla radice e `config.yaml`
dentro la cartella dell'app. Niente si rompe. Ma tutta la documentazione di
Vivavoce che dice *«Impostazioni → Componenti aggiuntivi»* — `README.md:107`,
`ha-addon/DOCS.md`, `repository.yaml:3` — descrive un menu che **non si chiama
più così da sei mesi**. Roba da T3.4.

### 1.4 Cosa NON sono riuscito a verificare

Elenco senza attenuanti. Ognuna di queste è un buco che va chiuso prima o
durante T3.3, non una cosa da dedurre adesso.

- **La qualità reale della ricerca `squeezebox` e di quella di MA.** Tutto ciò
  che dico in §1.2 viene dalla lettura del sorgente. Non ho un HA con LMS su
  cui misurare cosa succede davvero con «Comfortably Numb». **È la prima cosa
  da provare.**
- **Le regole di licenza di HACS.** Ho letto `hacs.xyz/docs/publish/start`,
  `/publish/integration` e `/publish/include`: elencano struttura del repo,
  `hacs.json`, `manifest.json` (domain, documentation, issue_tracker,
  codeowners, name, version), directory `brand` con `icon.png`, GitHub Action
  HACS + Hassfest verdi, una release completa (non un tag), topic e
  descrizione. **Della licenza non parlano.** Non ne deduco che AGPL vada bene:
  ne deduco che non c'è una regola scritta, il che è una cosa diversa e va
  chiesta a loro.
- **Le regole sul codice proprietario nelle App/add-on repository.**
  `developers.home-assistant.io/docs/apps/repository` documenta solo
  `repository.yaml` (name, url, maintainer) e come si aggiunge un repository
  custom. Nessun vincolo di licenza o contenuto scritto da nessuna parte.
  Anche qui: assenza di regola trovata ≠ permesso.
- **Che il Supervisor *mostri* il `CHANGELOG.md` dell'app prima di un
  aggiornamento.** La documentazione lo raccomanda accanto a `config.yaml` e
  motiva così: gli utenti «vedranno un avviso di aggiornamento e probabilmente
  vorranno sapere cosa è cambiato». Ma **non dichiara nessun contratto di
  rendering** — non dice dove appaia, né se appaia. Il file va scritto lo
  stesso (è raccomandato e serve a chi legge il repository), ma nessun documento
  di Vivavoce deve promettere quel comportamento dell'interfaccia finché
  qualcuno non lo vede su un HA vero.
- **La stringa italiana del menu dopo il rename.** Che in inglese
  `Settings → Add-ons` sia diventato `Settings → Apps` è nel blog ufficiale
  («add-ons are now called apps»). Che l'italiano sia **«App»** al posto di
  «Componenti aggiuntivi» viene da fonti terze, non dalla documentazione
  primaria. Per questo la documentazione di Vivavoce cita il nome nuovo e
  affianca quello vecchio per chi sta su HA precedente a 2026.2: se la
  traduzione fosse un'altra, il lettore ha comunque di che orientarsi.
- **Se Music Assistant richieda un CLA per i contributi.** Non ho trovato
  `CONTRIBUTING.md` né in root né in `.github/` su `music-assistant/server`
  (404 su entrambi, 2026-08-26). Il README rimanda a una sezione "Contributing"
  che non ho aperto. **Per l'opzione (d) questa è la prima domanda da fare, e
  va fatta a una persona, non a un file.**
- **Quale delle tre opzioni di `voice-support` sia realmente usata.** Il
  changelog del blueprint locale si ferma al 2025-04-04 mentre il repository è
  stato aggiornato il 2026-08-24: i due dati non si spiegano a vicenda e non so
  quale strada la community abbia effettivamente preso.
- **Se il blueprint italiano abbia un difetto reale nel calcolo del
  `media_type`.** La variabile `media_name` viene usata in
  `'radio' if 'radio' in media_name | lower else trigger_id` senza essere
  definita in `variables`. Sospetto sia un residuo, ma non l'ho eseguito e non
  lo affermo.
- **Quanti utenti HA abbiano MA, o *Search and Play* attivo, o parlino
  italiano.** Nessun dato pubblico trovato. Ogni ragionamento su "quanti"
  in questo documento sarebbe inventato, quindi non ce n'è nessuno.
- **La versione HA che ha introdotto `assist_satellite.ask_question`**: 2025.7
  secondo il blog di rilascio, ma la pagina dell'azione non la dichiara.

---

## 2. Le quattro opzioni

Costi in giornate-uomo su una stima a occhio di chi ha letto il codice, non su
un preventivo. Il rischio è "cosa può rendere inutile il lavoro fatto".

### (a) Conversation agent HA custom che inoltra all'engine via HTTP

Un'integrazione custom Python in `custom_components/vivavoce/`, con una
`ConversationEntity` (verificato il 2026-08-26 sulle docs core): eredita da
`homeassistant.components.conversation.ConversationEntity`, dichiara
`supported_languages` (`["it", "en"]`), implementa `_async_handle_message` che
riceve un `ConversationInput` (`text`, `context`, `conversation_id`,
`language`) più il `ChatLog`, e restituisce un `ConversationResult`
(`conversation_id`, `response`, **`continue_conversation`**). Dentro:
una POST al server Vivavoce, la risposta dell'engine come speech.

`continue_conversation` è il motivo per cui questa opzione esiste. È l'unico
punto di tutta l'architettura HA in cui «Quale intendi? 1, 2, 3» → «la 2»
funziona ovunque — satellite, app companion, dashboard — perché è l'agente
stesso a dire ad Assist di restare in ascolto.

- **Costo**: 3-5 giornate. Integrazione custom + config flow + mappatura
  `conversation_id` → sessione dell'engine + `brand/icon.png` + release HACS.
  Richiede **T3.2**: senza un `/api/v1` versionato l'integrazione si aggancia
  a un endpoint interno e si rompe alla prima rifattorizzazione.
- **Rischio**: **alto sull'adozione, basso sulla tecnica.** L'agente si
  seleziona nella pipeline Assist ed è **esclusivo**: dal momento in cui
  l'utente sceglie Vivavoce, tutto il resto (luci, timer, clima) passa da noi.
  O l'agente rigira ad Assist ciò che non capisce — codice in più, e il punto
  in cui l'integrazione diventa un pezzo di infrastruttura che deve non
  sbagliare mai — oppure chiediamo all'utente di **rinunciare** all'assistente
  di casa per la musica. Nessuna delle due è una richiesta piccola.
- **Licenza**: pulita. L'integrazione è un client sottile, tutta AGPL-3.0,
  **zero file proprietari** — il gate Pro resta dove è già, nel server
  Vivavoce. HACS distribuisce sorgente, il che con un'integrazione AGPL è
  esattamente ciò che deve succedere. **Ma**: un'integrazione AGPL non entrerà
  **mai** in HA core (Apache-2.0). La strada "un giorno in core" si chiude
  qui, e va chiusa con gli occhi aperti.
- **Monetizzazione/posizionamento**: il punto d'incontro con l'utente resta
  Vivavoce. Chi installa l'integrazione ha installato il server, e il server è
  dove vivono le distinzioni fra ciò che è libero e ciò che non lo è.

### (b) Intent handler custom per gli intent media di Assist

Registrare handler propri con `intent.async_register` (sottoclasse di
`intent.IntentHandler` con `intent_type`, `slot_schema`, `async_handle`), più
frasi custom.

Ci sono due sotto-varianti, e **la seconda è quella interessante**:

- **(b1) Un intent nuovo, es. `VivavocePlayMedia`.** Serve comunque
  un'integrazione custom in Python *e* le frasi che lo attivano. Rispetto ad
  (a) si guadagna la convivenza con Assist — l'agente resta quello di casa — e
  si perde `continue_conversation`, perché un `IntentResponse` chiude il turno
  come lo chiude un trigger. Cioè si perde la ragione per cui esiste Vivavoce.
- **(b2) Sovrascrivere `HassMediaSearchAndPlay`, oppure esporre un
  `media_player` con `SEARCH_MEDIA`.** Tecnicamente elegantissimo: un'entità
  che implementa `async_search_media` con il matching di Vivavoce eredita
  *Search and Play* gratis in diciannove lingue senza scrivere una frase. E
  tecnicamente inutile ai nostri fini, perché il contratto di
  `media_player.search_media` è **restituire una lista**; la scelta la fa
  l'intent con `results[0]`. Potremmo ordinare la lista molto meglio di
  `squeezebox` — è già un miglioramento reale, e per l'italiano è comunque
  irraggiungibile finché mancano le frasi — ma **la domanda «quale intendi?»
  non ha dove passare.** Il collo di bottiglia non è dove cerchiamo: è
  l'intent, e l'intent non è nostro.

- **Costo**: (b1) 3-4 giornate; (b2) 4-6, più la manutenzione di un'entità
  `media_player` completa.
- **Rischio**: **medio-alto, ed è il rischio peggiore**: si costruisce dentro
  un contratto che appartiene a HA core. Il giorno in cui *Search and Play*
  imparasse a chiedere, (b2) diventerebbe superflua — e sarebbe una buona
  notizia per tutti tranne che per il lavoro fatto.
- **Licenza**: come (a).
- **Monetizzazione/posizionamento**: la peggiore delle quattro. In (b2)
  Vivavoce **sparisce**: l'utente dice una frase di Home Assistant, sente
  rispondere Home Assistant, e non ha nessun motivo per sapere che il brano
  giusto è partito grazie a noi. Regalare il differenziale rendendolo
  invisibile è il modo più caro di regalarlo.

### (c) Innestarsi *sopra* Search and Play — lo strato dei blueprint

Un blueprint Vivavoce, cioè un'automazione con `trigger: conversation` e le
frasi italiane e inglesi che l'utente già usa («metti Comfortably Numb dei
Pink Floyd»), che chiama un `rest_command` verso il server Vivavoce e
restituisce con `set_conversation_response` **la frase che l'engine ha già
prodotto** — quella che nomina titolo e artista di ciò che è davvero partito.

Funziona per un motivo solo, ed è il fatto verificato in §1.3: **i trigger
vengono valutati prima degli intent built-in.** Le frasi che matchiamo le
gestiamo noi; tutto il resto — inclusi *Search and Play* e i blueprint di MA
se l'utente li ha — passa oltre intatto. Nessuna disattivazione, nessuna
pipeline da riconfigurare, nessuna entità nuova.

Rispetto al blueprint di Music Assistant la differenza è il ciclo di ritorno:
loro annunciano ciò che hanno sentito, noi annunciamo ciò che è partito. È il
delta di prodotto intero, espresso in una riga di YAML.

- **Costo**: **1-2 giornate.** Un file YAML nel repo, una sezione in
  `DEPLOY.md`, un `rest_command` da documentare. Nessuna integrazione Python,
  nessun HACS, nessun processo di review, nessuna release da tagliare.
  **Funziona già oggi con l'add-on esistente**, che è la cosa che rende questa
  opzione difficile da battere.
- **Rischio**: **basso, e reversibile.** Se non attecchisce si cancella un
  file. Non crea superficie di manutenzione.
- **Limite dichiarato, e va detto forte**: il turno si chiude. Il flusso
  «quale intendi?» **non è disponibile** per chi parla dall'app o dalla
  dashboard. Su un `assist_satellite` si può usare `ask_question`, e vale la
  pena farlo. Altrove la risposta migliore possibile è: fare la scelta
  migliore *e dire quale si è fatta* — che è comunque l'inverso del silenzio
  di `results[0]`, ma non è la promessa completa del README. Un ripiego
  praticabile senza satellite è una seconda frase-trigger («metti la due») che
  raccoglie i candidati che l'engine tiene già in sessione: costa poco, ma
  è un secondo turno che l'utente deve iniziare da sé, non una domanda che
  l'assistente gli fa.
- **Licenza**: nessuna implicazione. Un blueprint YAML nel repo AGPL.
- **Monetizzazione/posizionamento**: **la migliore.** Chi installa il
  blueprint deve avere il server Vivavoce, e ci arriva **dal repository di
  Vivavoce**, non da HACS o dallo store. Il rapporto con l'utente resta
  diretto; il gate Pro non si muove di un millimetro.

### (d) La via collaborativa — contribuire il matching a Music Assistant

Portare `engine/actions.py` (parsing titolo/artista/album, ranking
artist-aware, "did you mean") dentro Music Assistant, in cambio di visibilità.

- **Costo**: 5-10 giornate di codice — e non è quello il costo vero. Il costo
  vero è **portare `engine/` da AGPL-3.0 ad Apache-2.0**, perché MA è
  Apache-2.0 e non accetterà mai un contributo AGPL. Luca **può** farlo: ho
  verificato il 2026-08-26 che `git log --format='%an' -- engine/` restituisce
  **un solo autore**, quindi non serve il consenso di nessuno.
- **Rischio**: **irreversibile.** Non è "regalare il codice" — Vivavoce lo
  regala già, è AGPL. È **rinunciare all'asimmetria**: oggi chiunque riusi
  l'engine in un prodotto di rete deve aprire il suo (AGPL §13); il giorno
  dopo la relicenza, chiunque può chiuderlo. Si può rifare il percorso
  all'indietro sul proprio codice, ma non si può *disfare* quello che nel
  frattempo è finito in un progetto Apache con tremila stelle. E c'è un
  secondo rischio, meno drammatico e più probabile: **è un contributo che può
  semplicemente non essere accettato**, o essere accettato in una forma che
  non assomiglia più a ciò che è stato scritto — perché il pezzo che serve non
  è un algoritmo, è un *comportamento conversazionale* che l'architettura a
  intent di HA oggi non ha dove ospitare (§2.b2). Non ho verificato se MA
  richieda un CLA: se lo richiede, il costo cambia ancora.
- **Licenza**: la decisione più pesante del documento.
- **Monetizzazione/posizionamento**: la visibilità non è garantita da nessuna
  parte e non è oggetto di contratto. In cambio, il differenziale dichiarato
  nel README — «mai il brano sbagliato in silenzio» — diventa una funzione
  standard dell'ecosistema. Il che è una bella cosa per il mondo, e va detto,
  ma è il contrario di una posizione difendibile.

### Confronto

| | Costo | Rischio | Convive con Assist | «Quale intendi?» | Serve T3.2 | Licenza | Vivavoce è visibile |
|---|---|---|---|---|---|---|---|
| **(a)** agent custom | 3-5 gg | Alto (adozione) | Solo con fallback scritto da noi | **Sì, ovunque** | **Sì** | AGPL pulita, mai in core | Sì |
| **(b1)** intent custom | 3-4 gg | Medio | Sì | No | Sì | Come (a) | Poco |
| **(b2)** entità `SEARCH_MEDIA` | 4-6 gg | **Alto** (contratto altrui) | Sì | **No, per costruzione** | Sì | Come (a) | **No** |
| **(c)** blueprint | **1-2 gg** | **Basso, reversibile** | **Sì, per costruzione** | Solo su satellite | No | Nessuna | **Sì** |
| **(d)** contributo a MA | 5-10 gg + relicenza | **Irreversibile** | n/a | Da negoziare | No | **AGPL → Apache** | Come "grazie" |

---

## 3. Raccomandazione

**(c) adesso, (a) dopo T3.2 e solo se (c) produce utenti. (b) mai. (d) non
adesso, e con una condizione precisa.**

Il ragionamento in tre passaggi.

**Primo: (c) è l'unica opzione che si può sbagliare senza pagarla.** Costa un
file YAML, funziona con l'add-on che esiste già, non chiede all'utente di
rinunciare a niente, e non introduce nessuna superficie da mantenere. Se dopo
tre mesi nessuno l'ha installata, è un file da cancellare. Tutte le altre
chiedono di scommettere prima di sapere.

**Secondo: (a) è l'unica che mantiene la promessa intera, e va tenuta in
tasca.** «Quale intendi?» è la ragione per cui questo prodotto esiste, e
`continue_conversation` è l'unico punto di HA in cui quella domanda si può
fare a chiunque, ovunque. Ma è una scommessa che si fa una volta, e va fatta
*dopo* aver visto qualcuno arrivare da HA — non prima. In più ha un
prerequisito duro (T3.2) che oggi non è pronto.

**Terzo: la finestra non è quella che sembra.** La roadmap la immaginava come
"quanto tempo prima che MA faccia la voce". La verifica dice altro: il divario
è nell'*intent* di HA core, `results[0]`, che è una scelta di design
dichiarata e non scade da sola. Ciò che può chiudersi in fretta è l'altra
cosa, quella su cui abbiamo insistito di più: **le frasi italiane sono una PR
di traduzione.** Se domani qualcuno traduce `HassMediaSearchAndPlay` in
italiano, la parte di vantaggio che dipende dalla lingua evapora in una
release — e resta solo quella che dipende dal comportamento (artista,
streaming, disambiguazione), che è più solida ma più difficile da spiegare in
una frase. Un blueprint pubblicato ora è anche un modo per esserci **prima**
che quella PR arrivi.

Su **(d)**: non è da scartare, è da **rimandare a dopo una risposta.** La
domanda da fare, e da fare a una persona di Music Assistant prima di scrivere
qualunque riga: *«accettereste un contributo che rende `music_assistant.search`
capace di restituire un verdetto — "questo è quello giusto" / "questi tre sono
ambigui" — invece di una lista piatta?»* Se la risposta è sì, (d) diventa
interessante **senza toccare `engine/`**: si contribuisce l'idea e
un'implementazione scritta per loro, non si relicenzia il nostro. Se la
risposta è no o è vaga, (d) è chiusa e non torna. Nel frattempo, i blueprint
di `voice-support` sono Apache-2.0 e accettano contributi dichiaratamente
(*«Community driven effort»*): **il canale a costo zero verso quella comunità
è mandare lì un blueprint, non il codice.**

### Il primo passo implementabile

Un solo file nuovo, `blueprints/vivavoce_assist.yaml`, più la sezione che lo
documenta in `DEPLOY.md`. Contenuto:

1. Un input per l'URL del server Vivavoce (default `http://localhost:8730`, che
   è già giusto per chi usa l'app HA) e uno per la lingua.
2. Cinque `trigger: conversation` con le frasi che il router già capisce —
   quelle del README, **non** quelle di MA: «(metti|riproduci|fai partire)
   {query}», più le varianti inglesi. Il parsing di titolo/artista/album resta
   dove sta, in `engine/`, che è il punto: al blueprint bastano frasi larghe,
   perché il lavoro fine lo fa il server.
3. Un `rest_command` in POST verso `/api/v1/command` (fino a T3.2, `/command`
   — vedi §5) con `{text, lang}` più `client` derivato da `trigger.device_id`,
   così ogni satellite ha la sua sessione di candidati.
4. `set_conversation_response: "{{ response.json.speech }}"` — la frase che
   l'engine ha già costruito, che nomina ciò che è davvero partito.
5. Una **seconda** automazione nello stesso blueprint per il follow-up: se
   `response.json.choices` non è vuoto e il trigger arriva da un
   `assist_satellite`, `ask_question` con le tre alternative come `answers`;
   altrimenti nessuna domanda — la risposta dice cosa ha scelto e basta.
   Questo ramo va scritto **dichiarando in-page il limite**, non nascondendolo.

Costo reale stimato: una giornata scarsa per il YAML, mezza per la
documentazione, e mezza per la verifica sul campo di §1.2 — che vale la pena
fare nello stesso pomeriggio, perché è l'unico modo di sapere se il confronto
con l'esistente è quello che il sorgente lascia credere.

---

## 4. Cosa fa Vivavoce se l'utente ha già *Search and Play* attivo

**Convivenza. Esplicitamente e per costruzione — non sostituzione.** Questa è
la risposta, e vale per l'opzione raccomandata (c).

Il meccanismo non è un compromesso né un accordo: è l'ordine di
`DefaultAgent._async_handle_message` verificato in §1.3. I sentence trigger
vengono provati prima degli intent predefiniti. Quindi:

- una frase che matcha un trigger Vivavoce — «metti Comfortably Numb dei Pink
  Floyd» — **non arriva mai** a `HassMediaSearchAndPlay`;
- una frase che non matcha — «play some jazz», «play Rumours», qualunque cosa
  nelle altre diciassette lingue — **prosegue intatta** verso l'intent built-in
  e si comporta esattamente come prima che Vivavoce fosse installato;
- nessuna entità viene nascosta, nessuna pipeline riconfigurata, nessuna
  integrazione disabilitata. **Disinstallare Vivavoce = cancellare
  un'automazione.**

Sono due prodotti diversi e la convivenza non è una cortesia, è la
constatazione che fanno due cose diverse. *Search and Play* è **copertura**:
diciannove lingue, qualunque `media_player` con `SEARCH_MEDIA`, e una risposta
sempre — quella del primo risultato, giusto o sbagliato che sia. Vivavoce è
**precisione su un dominio stretto**: LMS/Daphile, italiano e inglese, TIDAL e
Qobuz, filtro per artista, e la disponibilità a *non* rispondere quando la
risposta sarebbe un tiro a indovinare. Chi ha un impianto hi-fi non vuole
sostituire il primo: vuole che le frasi che gli stanno a cuore vengano prese
sul serio, e che tutto il resto continui a funzionare.

**Con l'opzione (a) la risposta sarebbe diversa, e va scritta qui perché è il
motivo per cui (a) non è il primo passo.** Un `ConversationEntity` custom
**sostituisce** l'agente della pipeline: da quel momento Vivavoce riceve
*tutto*, timer e luci compresi. Convivere diventerebbe un lavoro nostro — un
fallback esplicito verso il default agent per ogni frase che non riconosciamo
— e vorrebbe dire mettersi sul percorso critico dell'assistente di casa di
qualcun altro. Se un giorno si farà (a), quel fallback non è un dettaglio
implementativo: **è il primo requisito**, e va nei test prima che nel codice.

---

## 5. Impatto su T3.2 e T3.4

### T3.2 — `/api/v1` per client esterni

Lo spike **conferma l'ordine deciso in roadmap** (T3.1 prima, T3.2 dopo) e
aggiunge un dato: **l'opzione raccomandata non ha T3.2 come prerequisito
bloccante.** Un blueprint può chiamare `POST /command`
(`localvoice/http_api.py:333`) così com'è, oggi. Ma allora quel percorso
diventa un contratto *de facto* verso il mondo esterno, e la roadmap dice —
giustamente — che i contratti si dichiarano invece di lasciarli formare da
soli. Quindi: il blueprint chiama `/command` **con una nota scritta nel file**
che quel percorso migrerà a `/api/v1/command`, e T3.2 lo ratifica.

Cosa lo spike dice a T3.2 sul **contratto**, in concreto:

- La forma che serve al client HA c'è già quasi tutta. `Router.handle_many()`
  (`localvoice/router.py`) restituisce
  `{speech, used, ok, terms, choices, unmatched}`, e `Router._choices()`
  (`localvoice/router.py`) produce già la lista numerata. Manca **una cosa
  sola** perché sia usabile da un agente: un flag esplicito tipo
  `needs_choice`, invece di lasciar dedurre al chiamante che `choices` non
  vuoto significa "ho chiesto e non ho suonato". Un blueprint YAML non è il
  posto dove fare deduzioni.
- **La sessione è già lì e va promossa a contratto.** Il router tiene i
  candidati per client con scadenza (`Router.candidates`, `Router.cand_until`,
  `Router._expire_candidates()` in `localvoice/router.py`), ed è
  esattamente la semantica di `conversation_id` in HA. Il campo oggi si chiama
  `client` nel payload di `/command`; in `v1` va nominato e documentato per
  quello che è — **il campo su cui un agente mappa il proprio
  `conversation_id`** — insieme al TTL, perché un client esterno deve sapere
  quanto tempo ha per dire «la 2».
- `room` (già previsto in roadmap) trova qui la sua prima ragione d'uso reale:
  l'area di HA da cui arriva il comando.
- L'inventario di `docs/api.md` deve dire, per ciascun endpoint, **se un client
  HA lo userà**. Oggi la risposta è: `/command` sì; `/players` e `/nowplaying`
  probabilmente sì (un `media_player` di cortesia, in futuro); `/license`,
  `/tls`, `/asr`, `/kidsafe`, `/wakeword` **no, mai** — sono la pagina, non il
  contratto, e la roadmap lo dice già per i primi due.

### T3.4 — il destino dell'add-on (oggi: *app*) che esiste già

Lo spike dà a T3.4 la risposta che aspettava: **promuovere, non ritirare.**
L'opzione (c) *ha bisogno* che il server Vivavoce giri accanto a Home
Assistant, e l'app è il modo più corto per ottenerlo — un click su HAOS,
`host_network: true` già impostato (`ha-addon/config.yaml`), auto-discovery
LMS che funziona senza configurazione. Senza l'app, il blueprint chiederebbe
all'utente di installare un container a mano prima di poter provare qualcosa:
è lì che si perdono le persone.

Cose concrete che lo spike ha trovato e che T3.4 deve chiudere:

- **Il rename Add-ons → Apps di HA 2026.2** rende obsoleto ogni riferimento a
  «Componenti aggiuntivi» nell'interfaccia: `README.md:107`, `repository.yaml:3`,
  `ha-addon/DOCS.md`. `repository.yaml` e `config.yaml` restano validi
  (verificato sul repository di esempio ufficiale, aggiornato 2026-07-30):
  **è documentazione da correggere, non uno schema da migrare.**
- **Mancano `icon.png` e `logo.png`.** Il repository di esempio li ha
  entrambi accanto a `config.yaml`; `ha-addon/` contiene solo `DOCS.md`,
  `Dockerfile`, `README.md`, `build.yaml`, `config.yaml`, `run.sh`. Oggi
  Vivavoce compare nello store con l'icona generica. Le icone del PWA esistono
  già (`localvoice/icon-192.png`, `icon-512.png`): è mezz'ora.
- **Manca `CHANGELOG.md` nella cartella dell'app**, che la documentazione
  raccomanda accanto a `config.yaml` perché chi riceve un avviso di
  aggiornamento vorrà sapere cosa è cambiato. Il `CHANGELOG.md` in radice
  c'è; qui serve quello dell'app. (Che il Supervisor lo renderizzi davvero
  nell'interfaccia di aggiornamento **non è documentato** — vedi §1.4.)
- `ha-addon/config.yaml` dichiara ancora `version: "0.2.0"` mentre `DEPLOY.md`
  documenta `:0.3.0` come tag dell'immagine. **`RELEASING.md` esiste
  esattamente per questo**, e `tests/test_packaging.py` verifica che i due file
  di versione concordino: la discrepanza è fra la versione dell'app e la
  documentazione, ed è il tipo di cosa che T3.4 deve chiudere insieme al resto.

- Il gate Pro non cambia e non deve cambiare: l'app installa il server, il
  server è dove vive la licenza. Il blueprint di (c) non introduce **nessun**
  nuovo punto di decisione su cosa è libero e cosa no — che è, di per sé, un
  argomento a favore di (c).

> **Chiuso da T3.4 il 2026-08-26.** Le prime quattro cose sono fatte (la
> quinta non era da fare: il gate Pro resta dov'era, che era il punto).
> Artwork generato da `tools/make_icons.py`, `ha-addon/CHANGELOG.md` scritto,
> rename applicato alla documentazione, e `DEPLOY.md` corretto a `:0.2.0` —
> **correggendo la documentazione, non bumpando la versione**, perché il bump
> e il tag vanno insieme. La deriva sulle versioni citate nei doc ha ora un
> test che la coglie (`test_docs_quote_the_declared_version`), che è ciò che
> mancava: i due file di versione erano guardati, la documentazione no.
> I riferimenti di riga qui sopra (`README.md:107`, `repository.yaml:3`) sono
> quelli di prima del rename e non puntano più dove dicono: restano perché
> questo documento è un reperto datato, non una guida da seguire oggi.

---

## Fonti

Tutte consultate il **2026-08-26** salvo dove indicato. Le voci marcate
**[sorgente]** sono state lette nel codice, non nella documentazione — è la
differenza fra "le docs dicono" e "il programma fa".

**Home Assistant — core e documentazione per sviluppatori**
- **[sorgente]** `home-assistant/core`, branch `dev`,
  `homeassistant/components/media_player/intent.py` — `MediaSearchAndPlayHandler`,
  `results[0]`, `slot_schema`.
- **[sorgente]** `homeassistant/components/conversation/default_agent.py` —
  `_async_handle_message`, precedenza dei sentence trigger.
- **[sorgente]** `homeassistant/components/squeezebox/media_player.py` e
  `manifest.json` — `SEARCH_MEDIA`, `async_search_media`, tipi cercati.
- **[sorgente]** `homeassistant/components/music_assistant/services.yaml` —
  schema di `play_media`, `search`, `play_announcement`, `transfer_queue`.
- <https://developers.home-assistant.io/docs/core/entity/conversation/> —
  `ConversationEntity`, `_async_handle_message`, `ConversationResult`.
- <https://developers.home-assistant.io/docs/intent_handling/> —
  `intent.async_register`, `IntentHandler`.
- <https://developers.home-assistant.io/docs/intent_builtin/> — intent media.
- <https://developers.home-assistant.io/docs/apps/repository/> — repository di
  app; rename add-on → app.
- <https://github.com/home-assistant/addons-example> — struttura di riferimento
  (ultimo push 2026-07-30).
- <https://www.home-assistant.io/actions/assist_satellite.ask_question/> e
  <https://www.home-assistant.io/blog/2025/07/02/release-20257/> — `ask_question`.
- <https://www.home-assistant.io/integrations/conversation/> — «Prefer handling
  commands locally».
- <https://www.home-assistant.io/docs/scripts/> — `set_conversation_response`.
- <https://www.home-assistant.io/blog/2026/08/05/release-20268/> — controllo che
  non ci fossero novità su intent media (non ce ne sono).
- <https://www.home-assistant.io/blog/2026/02/04/release-20262/> (via ricerca) —
  rename Add-ons → Apps.

**Intent e lingue**
- **[sorgente]** `OHF-Voice/intents`, listato via API: `sentences/it/` (33
  intent, senza `HassMediaSearchAndPlay`) contro `sentences/en/`; le 19 lingue
  che hanno l'intent.

**Music Assistant**
- <https://www.music-assistant.io/installation/> — app HA e Docker.
- <https://www.music-assistant.io/integration/voice/> — *Search and Play* e i
  suoi limiti dichiarati; i tre blueprint.
- <https://www.music-assistant.io/plugins/fastmcp-server/> — plugin MCP,
  trasporto, token, avvisi di sperimentalità.
- <https://www.home-assistant.io/integrations/music_assistant/> — le sei azioni.
- **[sorgente]** `music-assistant/voice-support` — `README.md`,
  `local-assist-blueprint/mass_assist_blueprint_it.yaml` (210 righe, letto per
  intero), `changelog.md`; metadati via API (Apache-2.0, 319 stelle, push
  2026-08-24).
- **[sorgente]** `music-assistant/server` — licenza Apache-2.0, 2.979 stelle
  (via API); `CONTRIBUTING.md` **non trovato** (404 in root e in `.github/`).
- **[sorgente]** `music-assistant/intents` — Apache-2.0, solo `en`, fermo dal
  2024-11-24.
- <https://www.music-assistant.io/blog/2026/06/10/music-assistant-2-9/> —
  riportato dalla nota di roadmap del 2026-08-25, **non ricontrollato qui**.

**HACS**
- <https://www.hacs.xyz/docs/publish/start/>,
  <https://www.hacs.xyz/docs/publish/integration/>,
  <https://www.hacs.xyz/docs/publish/include/> — `hacs.json`, `manifest.json`,
  `brand/icon.png`, HACS Action + Hassfest, release completa, PR su
  `hacs/default`, *«new additions still take months to be reviewed and
  included»*. **Nessun requisito di licenza documentato.**

**Vivavoce (questo repository)**
- `localvoice/http_api.py:333` — l'handler di `POST /command`.
- `localvoice/router.py` — `Router.handle_many()`, `Router._choices()`,
  `Router.candidates` / `cand_until` / `_expire_candidates()`: candidati di
  sessione e scadenza. (Riferimenti per simbolo e non per riga: il file è in
  lavorazione su un altro binario mentre questo documento viene scritto.)
- `ha-addon/config.yaml`, `repository.yaml`, `README.md:107`.
- `.omc/plans/vivavoce-roadmap.md` — T3.1 (nota del 2026-08-25), T3.2, T3.4.
