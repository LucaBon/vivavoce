# Nomi mal sentiti: indice fonetico, correzioni, varianti, Whisper

> Piano di lavoro. Stato: **deciso** (§5), implementazione in corso.
> Branch: `feature/riconoscimento-nomi`, da `develop` (`1c75695`).
> Ordine concordato: **1 + 2**, poi **4**, infine **3**.
> Verifiche fatte per questo documento: **2026-11-19**.

---

## 0. Il problema, con due casi veri

Il riconoscitore vocale trascrive bene le parole che conosce e *corregge*
verso di esse quelle che non conosce. Con nomi stranieri e rari il testo che
arriva a Vivavoce è già sbagliato, e la ricerca fa onestamente il suo lavoro
sul testo sbagliato.

| Detto | Trascritto (Edge, it-IT) | Cosa succede oggi |
|---|---|---|
| «metti Kamin di EMIN e JONY» | «metti coming di eminem e johnny» | cerca Eminem |
| «metti Kamin» | «metti camin» | offre tre brani occitani/portoghesi con «camin» nel titolo; «Kamin» non c'è |

Due difetti distinti:

1. **Trascrizione**: «EMIN» → «eminem», «Kamin» → «coming». Nessuna regola
   di grafia ci arriva: serve sapere *quali nomi esistono* (fasi 1, 2, 3).
2. **Ortografia**: «camin» è foneticamente giusto, ma la ricerca dei servizi
   streaming confronta lettere, non suoni (fasi 1, 4).

## 1. Vincoli del progetto che il piano rispetta

- **Solo voce, solo Pro** (decisione §5.1). Tutto questo piano serve a
  rimediare agli errori del *riconoscimento vocale*, e il microfono è Pro.
  Nella casella di testo si scrive già il nome come va scritto: un comando
  scritto non viene mai riscritto, corretto o allargato da niente di quanto
  segue. Il server deve quindi sapere se un turno è stato detto o scritto:
  il campo `via` (§2) arriva al passo 0, non alla fase 2.
- **Dove sta il codice.** Lo schema è quello di kid-safe e multi-room: il
  core (AGPL) espone un aggancio che riceve un oggetto funzione iniettato,
  `None` = funzione spenta; l'oggetto vive in `localvoice/pro/` (EULA Pro) e
  lo costruisce `localvoice/pro_features.py`. Nel core finiscono solo il
  campo `via`, l'aggancio e l'evento «ho riprodotto X» per lo storico; chiave
  fonetica, indice, correzioni e varianti stanno in `localvoice/pro/`.

- **Core stdlib-only** (`engine/`, `localvoice/`): l'algoritmo fonetico è
  scritto a mano, niente `jellyfish`/`metaphone`.
- **L'engine non nomina mai un backend**: le fonti dell'indice passano da
  metodi del protocollo, gated da `Capabilities` (`engine/player/protocols.py`).
- **400 righe per file** (`tests/test_packaging.py`): moduli nuovi, non
  aggiunte a `matching.py` (335) o `router.py` (367).
- **Nessun test tocca la rete**; Python 3.9; `from __future__ import annotations`.
- **Budget di turno** `Router.TURN_BUDGET = 10.0` s: ogni ricerca in più
  (fase 4) deve stare dentro, non accanto.
- **Lingua per richiesta** (`messages.set_lang()` è una `ContextVar`): regole
  fonetiche e correzioni sono per lingua.
- **Kid-safe**: nessuna riscrittura può aggirare il `Guard`. Regola: si
  riscrive *il testo*, e il testo riscritto rifà il percorso normale, guard
  compreso. Mai riprodurre direttamente un elemento dell'indice.
- **Privacy** (`PRIVACY.md` elenca *ogni* dato salvato): indice e correzioni
  sono nuovi file in `data_dir`, vanno dichiarati lì.

## 2. Cosa c'è già e va tenuto in conto

- `localvoice/alternatives.py` (`AlternativeSweep`): prova le alternative di
  Web Speech (fino a 5) in ordine e si ferma al primo colpo. **Si ferma anche
  su un'OFFER** («ne ho diversi per camin…»): un'offerta debole della prima
  alternativa toglie la parola alle altre. La fase 1 deve cambiare questo
  punto, con attenzione (il commento lì spiega perché oggi è così).
- `engine/matching.py`: `_score` è `difflib` su testo normalizzato,
  `CONFIDENT_SCORE` è la soglia di fiducia, `_trusts_ranking` distingue i
  servizi che rispondono «niente» (TIDAL, Qobuz) da Spotify, che risponde
  sempre.
- Whisper (`localvoice/pro/asr.py`) dà una sola alternativa: per chi lo usa
  l'indice è l'unica rete di sicurezza, finché non arriva la fase 3.
- Il client distingue già i turni scritti (`opts.typed` in `chat.js`) ma
  **non lo dice al server**: `/api/v1/command` riceve `text`,
  `alternatives`, `client`, `source`, `lang`, `player`. Le `alternatives`
  non bastano a riconoscere un turno vocale: la pagina le manda solo quando
  sono più di una, e Whisper ne dà sempre una.
- Fonti di nomi disponibili oggi: `favorites_items()` (LMS),
  `local_*_candidates(query)` (solo *per query*, non un elenco completo),
  `playlist_candidates(query)`. **Non esiste** un elenco completo di
  artisti locali né uno storico delle riproduzioni.

## 3. Misurare prima di cambiare

**Passo 0b — il campo `via`.** `/api/v1/command` accetta
`via: "voice" | "typed"`, opzionale; mancante vale `typed`, cioè «non
toccare niente», il default sicuro per i client che non lo conoscono (Home
Assistant, script). La pagina lo manda da `mic.js`, `localasr.js`, dal
wake word e dalla casella di testo. Documentato in `docs/api.md`.

**Passo 0a.** Un **corpus di regressione** in
`tests/data/misheard.json`, una voce per caso reale.

```json
{"lang": "it", "heard": ["metti coming di eminem e johnny"],
 "index": [{"title": "Kamin", "artist": "EMIN & JONY"}],
 "expect": {"title": "Kamin", "artist": "EMIN & JONY"}}
```

Insieme, il contrario: **casi che non devono cambiare** («metti Lose
Yourself di Eminem» con EMIN nell'indice deve restare Eminem; «metti camin»
senza Kamin nell'indice deve restare l'offerta di oggi). Ogni fase si misura
su questo corpus prima e dopo. Il rischio vero di tutto il piano è
*dirottare* richieste che oggi funzionano, non mancare quelle che falliscono.

---

## Fase 1 — Indice dei nomi noti e risoluzione fonetica

### 1.1 Chiave fonetica — `localvoice/pro/phonetic.py` (nuovo)

`phonetic_key(text, lang) -> str`: riduce un nome alla sua «pronuncia» in
lettere, in modo che grafie diverse dello stesso suono collidano.

- Normalizzazione esistente (`_fold`: minuscole, accenti tolti), poi regole
  per lingua, in una tabella dati per lingua come `connectors/` e `lang/`:
  - comuni: `k|q|c(+a/o/u)|ch → K`, `ph → F`, `w → V`, `y → I`,
    `x → KS`, `h` muta, doppie collassate, vocali finali deboli opzionali;
  - `it`: `gh → G`, `gn → NI`, `sc(+e/i) → S`, `j → I`;
  - `en`: `ee/ea → I`, `oo → U`, `sh → S`, `j → G`; `de`/`fr`/`es`: le loro
    (es. `fr`: `ou → U`, `eau → O`; `de`: `sch → S`, `ei → AI`).
- `phonetic_score(a, b, lang) -> float`: `difflib` sulle chiavi, combinato
  con `_score` sul testo (il massimo dei due, non la media: una grafia uguale
  resta un colpo pieno).
- Test di unità puri: `camin`/`Kamin`, `pink floid`/`Pink Floyd`, e coppie
  che **non** devono collidere (Metallica/Megadeth, Vasco Rossi/The Beatles).
- **Misurato** (passo 1a, 2026-11-20): `camin`/`Kamin` 1,00;
  `coming`/`Kamin` 0,73; «eminem e johnny»/«EMIN & JONY» 0,82;
  `emin`/`Eminem` **0,80**; Metallica/Megadeth 0,40; Vasco Rossi/The Beatles
  0,20. Quindi la chiave *ordina* e non decide: due artisti diversi possono
  stare a 0,80. La protezione dai dirottamenti (§3) sta nella fase 1c —
  si interviene solo se il giro normale non ha un colpo sicuro, con soglia
  **e** margine sul secondo — non nella chiave.

### 1.2 L'indice — `localvoice/pro/name_index.py` (nuovo)

Un elenco di `{title, artist, album?, kind, source, weight, last_seen}`,
con chiavi fonetiche precalcolate, in `data_dir/name_index.json` (scrittura
atomica come `blocklist_store._write_json_durably`).

Fonti, in ordine di valore:

1. **Storico di Vivavoce** (attivo di default, §5.4): ogni riproduzione
   andata a buon fine (titolo, artista, servizio) entra nell'indice con
   `weight` crescente a ogni ripetizione. Funziona per *tutti* i servizi,
   streaming compresi, senza chiedere niente a nessuna API. Lo storico si
   *registra* da tutti i turni, scritti compresi — un comando scritto è la
   fonte migliore della grafia giusta — ma si *usa* solo sui turni vocali.
   Nel core, l'engine emette un evento «ho riprodotto X» dove sa già di aver
   riprodotto (`_dispatch_play`, `_play_tidal_track`); senza un ascoltatore
   iniettato l'evento non va da nessuna parte.
2. **Preferiti LMS**: `favorites_items()`, gated da `Capabilities.favorites`.
3. **Libreria locale**: serve un metodo nuovo,
   `local_artists(count) -> List[Dict]` (e forse `local_albums`), nel
   protocollo `MusicLibrary` sotto `Capabilities.local_library`; per LMS è il
   comando CLI `artists 0 N`. `tests/test_player_protocol.py` lo terrà
   onesto su ogni backend.
4. (Più avanti, se serve) preferiti dei servizi streaming via i feed dei
   plugin LMS: costosi e fragili, fuori da questa fase.

Aggiornamento pigro con TTL (es. 6 h) e in un thread, mai nel percorso di un
turno; tetto di dimensione (es. 5 000 voci, scarta per `weight`/`last_seen`).

**Fatto (passo 1b, 2026-11-20).** Un solo aggancio nel router invece di uno
per ogni punto che riproduce: dopo un turno che ha suonato (`ok`, senza
`kind`, con `terms`), `Names.note_played` chiede *all'impianto* cosa sta
suonando, dopo 2 s e in un thread, e lo tiene solo se coincide con i
`terms` del turno (parole intere): un impianto ancora sul brano precedente
non entra nello storico. La grafia è quella del catalogo, che è il punto.
Con il multi-room si chiede al player su cui il turno ha suonato
(`ConversationState._aimed_at` lo ricorda). Lo storico persiste in
`name_index.json` (max 2 000); preferiti e artisti locali restano in memoria
e si rileggono ogni 6 h. Lo storico si *registra* da tutti i turni, anche
scritti; si *userà* solo su quelli vocali.

> **Da non unire prima della fase 2.** Da qui lo storico raccoglie dati, e
> l'interruttore per spegnerlo e svuotarlo arriva con la sezione delle
> impostazioni (fase 2). `PRIVACY.md` lo descrive già com'è a lavoro finito.

### 1.3 Dove interviene — aggancio in `localvoice/alternatives.py`

Solo con `via == "voice"` e licenza Pro, nel giro delle alternative, *dopo*
che il giro normale non ha trovato un colpo sicuro:

1. Per ogni alternativa: `parse_song_query` → titolo/artista; cerca
   nell'indice per chiave fonetica.
2. Accetta solo se il migliore supera una soglia **e** stacca il secondo di
   un margine (un nome ambiguo nell'indice non decide niente).
3. Riscrive il testo con i nomi canonici («metti Kamin di EMIN & JONY») e lo
   rimanda a `handle` **una volta** (niente ricorsione).
4. Lo dice: «Ho capito "camin": metto Kamin di EMIN & JONY.» Una
   correzione silenziosa che sbaglia è peggio di un'offerta.

E il punto dell'OFFER (§2): un'offerta il cui primo candidato sta sotto
`CONFIDENT_SCORE` non chiude più il giro *se l'indice ha un colpo sicuro*.
Se l'indice non ha niente, il comportamento resta quello di oggi.

**Fatto (passo 1c, 2026-11-20), con tre correzioni alla bozza qui sopra.**

1. *Il criterio non è `CONFIDENT_SCORE`.* Nel caso vero la lista dei tre
   brani occitani non è debole: «camin» è contenuto parola per parola nei
   loro titoli, `_score` dà 0,95. Il criterio è **«il turno non ha
   riprodotto»**: un mancato, una lista da scegliere (`kind` `list` o
   `disambiguate`) o un'offerta. Mai sopra una riproduzione, un gate
   (licenza, kid-safe), un impianto che non risponde, un «un attimo».
   Il giro normale resta intatto: l'indice si consulta *dopo*, una volta
   sola, sulla prima alternativa che suona come un nome noto.
2. *Una lista che contiene già il nome noto non si tocca.* «metti Love» con
   due «Love» in lista e uno nello storico: la domanda era giusta, e la
   risposta è dell'utente.
3. *L'artista nella frase riscritta solo se ne è stato detto uno.* La
   ricerca streaming separa titolo e artista, la libreria locale cerca la
   frase intera: «metti camin» diventa «metti Kamin», che capiscono entrambe.

Decisione: soglia `ACCEPT = 0.9`, margine `MARGIN = 0.1` sul secondo nome
*diverso* (lo stesso brano tenuto due volte è un nome solo; stesso titolo di
due artisti senza artista sentito è ancora una risposta sul titolo). La
frase riscritta rifà tutto il router — kid-safe, stanze, sorgenti — e se
riproduce chiude la lista della prima risposta; se manca anche lei, resta la
prima risposta, lista compresa. La risposta dice cosa ha sentito: «Ho sentito
«camin». Riproduco Kamin…».

Limiti noti, voluti per ora: solo il verbo generico («metti X», `generic_play`);
non le frasi con album, playlist o «la musica di». E una frase con stanza o
sorgente («metti camin in cucina», «metti camin da tidal») porta quelle
parole dentro il nome cercato nell'indice, e di solito non supera la soglia:
non sbaglia, semplicemente non aiuta.

---

## Fase 2 — Imparare dalle correzioni

### 2.1 Il segnale

Un turno **vocale** che non ha riprodotto, o ha offerto una lista da cui non
si è scelto niente, seguito entro ~90 s, dallo **stesso client**, da un
turno **scritto** che riproduce. Il secondo è la correzione del primo.

- Il segnale si legge dal campo `via` del passo 0b.
- `ConversationState` (per client) ricorda l'ultimo turno vocale: testo,
  alternative, esito, ora.
- Anche **toccare una scelta** dopo un turno vocale è una conferma, ed è il
  segnale più pulito di tutti.

### 2.2 Il rischio: imparare cose false

Chi dice «metti Vasco» e poi, deluso, scrive «metti i Queen» non sta
correggendo niente. Due difese:

- un minimo di somiglianza tra detto e scritto (testo o chiave fonetica);
- **conferma esplicita, sempre** (§5.2): sotto la risposta compare un chip
  «Ricorda: quando sento "coming di eminem e johnny" intendo questo». Un
  tocco, e la correzione è salvata. Senza tocco non si salva niente.

### 2.3 Applicarle — `localvoice/pro/corrections.py` (nuovo)

- `data_dir/corrections.json`: `{lang, heard_norm, heard_key, meant, hits,
  last_used}`, tetto 500, LRU.
- Prima del routing, per ogni alternativa: corrispondenza esatta del testo
  normalizzato (senza il verbo e senza la stanza, che con il multi-room
  cambiano da una volta all'altra), poi fonetica sopra soglia alta. Riscrive
  il testo e prosegue: il guard kid-safe lo vede comunque.
- Il nome «meant» entra anche nell'indice della fase 1, con peso alto.
- Gestione (§5.3): nelle impostazioni della pagina, accanto a kid-safe, una
  sezione «Nomi e correzioni» con l'elenco delle correzioni (cancellabili una
  per una), l'interruttore dello storico e un pulsante per svuotarlo. Per ora
  niente comandi vocali per cancellarle.

---

## Fase 4 — Varianti di grafia nella ricerca

Per i brani **mai incontrati**, che l'indice non conosce.

- Solo sui turni vocali Pro: il router passa a `play_song` un espansore di
  ricerca iniettato (stesso stile del `guard=`), `None` sui turni scritti.
- In `play_song` (poi artista e album), solo quando i risultati non hanno un
  candidato sopra `CONFIDENT_SCORE`: genera varianti del titolo e
  dell'artista con le regole inverse della chiave fonetica (`c → k`,
  `ch → k`, `i → y`, `f → ph`, `v → w`, doppie, per lingua).
- **Al massimo 2 ricerche in più**, e solo se il budget del turno lo
  consente (scadenza esplicita, non una speranza).
- Unisce i risultati e li ordina con `phonetic_score`. Su Spotify
  (`trust_ranking = False`) la soglia resta quella di `_resolved_enough`,
  perché lì «ha trovato qualcosa» non significa niente.
- Test con il trasporto simulato: «camin» trova «Kamin» se la variante
  `kamin` è nel catalogo finto; nessuna ricerca in più quando il primo
  giro è già sicuro (si conta quante ricerche partono).

---

## Fase 3 — Whisper guidato dai nomi noti

Verificato oggi sul wheel di `faster-whisper==1.2.1` (quello fissato da
`pyproject.toml` e dal Dockerfile): `WhisperModel.transcribe` accetta
`hotwords: Optional[str]` e `initial_prompt`. Gli hotwords vengono
tokenizzati e troncati a metà del contesto (~224 token): ci stanno circa
60–100 nomi.

- `Transcriber.transcribe(audio, lang, hotwords=None)`; il server passa una
  stringa costruita dall'indice (fasi 1 e 2): i nomi con più `weight`, più i
  «meant» delle correzioni, per la lingua della richiesta. Cache della
  stringa, ricostruita quando l'indice cambia.
- Test senza rete: un modello finto che registra gli argomenti ricevuti.
- Misura manuale con registrazioni vere (le due frasi del §0 e altre), perché
  l'effetto degli hotwords non si può simulare. Da fare sulla macchina
  dell'utente: qui non c'è audio.
- Rischio noto: hotwords troppo «forti» spingono Whisper a vedere nomi dove
  non ci sono. Va misurato sul corpus del §3 in negativo.

---

## 4. Ordine e dimensioni

| Passo | Cosa | File principali | Stima |
|---|---|---|---|
| 0a | Corpus di regressione | `tests/data/misheard.json`, `tests/test_misheard.py` | piccola |
| 0b | Campo `via` | `api_v1.py`, `router.py`, `chat.js`, `mic.js`, `localasr.js`, `docs/api.md` | piccola |
| 1a | Chiave fonetica | `localvoice/pro/phonetic.py` + test | media |
| 1b | Indice + fonti (storico, preferiti, `local_artists`) | `localvoice/pro/name_index.py`, evento di riproduzione nell'engine, `engine/player/*`, protocollo | grande |
| 1c | Risoluzione nel giro delle alternative + OFFER | `alternatives.py`, `pro_features.py` | media |
| 2 | Correzioni: segnale, chip, store, sezione impostazioni | `localvoice/pro/corrections.py`, `chat.js`, `index.html` | grande |
| 4 | Varianti di grafia | `localvoice/pro/spelling.py`, `actions.py` | media |
| 3 | Hotwords Whisper | `localvoice/pro/asr.py`, `audio_api.py` | piccola |
| — | `PRIVACY.md`, `CHANGELOG.md` a ogni fase | | piccola |

Ogni passo è un commit (o più) con i suoi test; e2e dove tocca la pagina.

## 5. Decisioni (prese il 2026-11-20)

1. **Tutto Pro, tutto solo voce.** Il microfono è Pro, e questi rimedi
   servono solo dove c'è il microfono: nella casella di testo il nome si
   scrive già giusto. Nessun comando scritto viene toccato.
2. **Correzioni: conferma sempre**, con il chip. Niente apprendimento
   automatico.
3. **Gestione nelle impostazioni, accanto a kid-safe.**
4. **Storico delle riproduzioni attivo di default**, spegnibile e
   svuotabile dalla stessa sezione. Da dichiarare in `PRIVACY.md`.
