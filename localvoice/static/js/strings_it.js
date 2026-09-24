// The Italian UI string table: every string built at runtime. The Italian
// labels are in the markup (snapshotted by initI18n); the English table and
// the notes on how the two are split are in strings_en.js.

import { MIC_WHY_IT, micWhy } from "./micerrors.js";

// Italian counterparts of the dynamic strings (the labels come from the markup).
export const UI_IT = {
  micstate_idle: "tocca e parla",
  micstate_listening: "in ascolto…",
  no_voice: "(nessuna voce)",
  ph_text: "es. riproduci Time dei Pink Floyd",
  mic_title: "Microfono: tocca e parla, tocca di nuovo per fermare",
  title_page: "Vivavoce — voce locale",
  status_tap_write: "Tocca il microfono e parla, oppure scrivi qui sotto.",
  status_locked: "Scrivi il comando qui sotto, è gratis. Il microfono è Pro: toccalo per saperne di più.",
  // Only the spoken half: the on-screen line is Italian markup already.
  // No product name here either — see the English side for why.
  ai_notice_spoken: "Assistente vocale automatico.",
  src_auto: "Automatica: libreria, poi streaming",
  src_local: "Solo la mia libreria",
  src_only: "Solo ",
  lms_down: "Non raggiungo il server musicale (LMS): controlla che sia acceso.",
  offline: "Questo dispositivo \u00e8 offline: controlla il Wi-Fi.",
  net_error: "Errore di rete verso il server locale.",
  no_mic: "Questo browser non supporta il microfono. Usa la casella di testo, oppure apri con Chrome/Edge.",
  need_https: "Il microfono richiede HTTPS quando apri da un altro dispositivo. Avvia il " +
    "server con un certificato (vedi README) oppure usa la casella di testo.",
  check_text: "Controlla il testo (occhio ai nomi inglesi) e premi Invia.",
  listening: "Ascolto…",
  listening_wake: (w) => "In ascolto… di' «" + w + " …»",
  // Il rifiuto di POST /wakeword/phrase, e la conferma. Una frase di cui il
  // motore non ha la pronuncia non peggiora: non si attiva mai. Quindi e' un
  // rifiuto da dire, non un avviso da addolcire.
  wake_phrase_rejected: (words) => "«" + words.join("», «") + "»: il motore sul server non ha la pronuncia "
    + (words.length > 1 ? "di queste parole" : "di questa parola") + ", quindi non la sentirebbe mai. Scegli una frase fatta di parole vere.",
  wake_phrase_saved: "Parola chiave salvata per tutta la casa.",
  wake_phrase_unverified: "Salvata, ma non confrontata col vocabolario del motore sul server: se non è una parola vera potrebbe non attivarsi mai.",
  wake_phrase_failed: (why) => "NON salvata per la casa (" + why + "). Questo dispositivo continua a rispondere; gli altri no.",
  wake_phrase_save_failed: "NON salvata per la casa: il server non riesce a scrivere nella sua cartella dati. Questo dispositivo continua a rispondere; gli altri no. Il log del server dice quale file.",
  say_command: "Sì? Dimmi il comando…",
  tap_mic: "Tocca il microfono e parla.",
  tap_to_resume: "Ascolto interrotto \u2014 tocca il microfono per riprendere.",
  wake_gave_up: (e) => "Ascolto continuo interrotto: " + micWhy(MIC_WHY_IT, e) +
    " Tocca il microfono per ricominciare.",
  mic_error: (e) => "Microfono: " + micWhy(MIC_WHY_IT, e),
  cmd_timeout: "Nessuna risposta dal server. \u00c8 ancora acceso?",
  still_working: "Sto ancora eseguendo il comando precedente\u2026",
  asr_working: "Trascrivo…",
  asr_failed: "Riconoscimento locale non riuscito: uso quello del browser.",
  lbl_controls: "Comandi",
  lbl_text: "Comando testuale",
  log_label: "Cronologia comandi",
  np_label: "In riproduzione",
  np_prev: "Brano precedente",
  np_play: "Riproduci",
  np_pause: "Pausa",
  np_next: "Brano successivo",
  np_seek: "Posizione nel brano",
  np_vol: "Volume",
  pro_activate: "Attiva",
  pro_key_lbl: "Chiave di licenza Pro",
  pro_buy: "Acquista la licenza Pro ↗",
  pro_pitch: "Microfono, parola chiave, voci di lettura, multi-stanza e kid-safe " +
    "sono funzioni <b>Pro</b> — licenza una tantum, tua per sempre. " +
    "Scrivere i comandi è gratis, sempre.",
  pro_active: (k) => "Pro attivo — licenza " + k + ". Grazie per sostenere il progetto!",
  pro_revoked: "Questa licenza risulta <b>disattivata o rimborsata</b>: le funzioni Pro " +
    "sono spente. Inserisci una chiave valida per riattivarle.",
  pro_err_network: "Non raggiungo il server delle licenze. Controlla la connessione e riprova.",
  pro_err_invalid: "Chiave non valida (o limite attivazioni raggiunto): ",
  pro_err_save: "Attivata \u2014 ma non sono riuscito a salvarla su questa macchina. Libera spazio sul disco e ricarica la pagina: la chiave \u00e8 gi\u00e0 registrata, non reinserirla.",
  pro_only: " — funzione Pro",
  pro_trial: (n) => "<b>Prova Pro — " + (n === 1 ? "ultimo giorno" : "restano " + n + " giorni") +
    ".</b> È tutto attivo, microfono compreso. Alla scadenza i comandi scritti " +
    "continuano a funzionare esattamente come ora: non si rompe niente, non si perde niente.",
  pro_trial_over: "<b>La prova Pro è finita.</b> Scrivere i comandi è gratis, sempre — " +
    "microfono, parola chiave, voci di lettura, multi-stanza e kid-safe tornano con " +
    "una licenza una tantum, tua per sempre.",
  upsell_spoken_trial: (n) => "👆 Questo potevi dirlo a voce. Tocca il microfono e " +
    "provalo — la prova Pro è attiva ancora per " +
    (n === 1 ? "un giorno" : n + " giorni") + ".",
  upsell_spoken_over: "👆 Questo potevi dirlo a voce. Il microfono è una funzione Pro — " +
    "scrivere resta gratis.",
  upsell_see_pro: "Scopri Pro",
  cert_state_ok: "<b>✅ Certificato installato.</b> Lucchetto verde, nessun avviso, e " +
    "l'app si può installare dal menu del browser (<b>Installa app</b> / <b>Aggiungi a " +
    "schermata Home</b>).",
  cert_state_untrusted: "<b>⚠️ Questo dispositivo non si fida ancora del certificato.</b> " +
    "È l'avviso che hai superato per arrivare qui — ed è il motivo per cui il microfono e " +
    "l'installazione dell'app sono bloccati. Due passi, una volta sola per dispositivo:",
  cert_state_nocert: "<b>⚠️ Questo dispositivo non si fida del certificato</b>, e questo " +
    "server non offre nessuna CA locale da installare. O usa un certificato tuo, o è stato " +
    "avviato senza <code>tools/make_cert.py</code> — vedi DEPLOY.md.",
  cert_state_http: "<b>Questa pagina arriva in HTTP semplice.</b> Da un altro dispositivo " +
    "il microfono non può funzionare — e nessun certificato installato qui lo cambierebbe: " +
    "prima il server deve servire HTTPS (vedi DEPLOY.md). I comandi scritti funzionano " +
    "così come sono.",
  cert_state_local: "<b>Sei sul computer che fa girare il server</b>, quindi non c'è " +
    "niente da installare: qui il microfono funziona già. È aprire la pagina dal " +
    "<i>telefono</i> che richiede HTTPS e questo certificato.",
  cert_state_unknown: "Questo browser non può verificare il certificato da solo. Se nella " +
    "barra degli indirizzi vedi un avviso invece del lucchetto, questi passi lo risolvono:",
  cert_verify_btn: "L'ho installata — ricontrolla",
  cert_other_btn: "Un altro dispositivo?",
  cert_other_hide: "Nascondi gli altri dispositivi",
  cert_steps: (p) => {
    const download = 'Scarica la CA locale: <a href="/ca.pem" download>ca.pem</a> ' +
      '(una volta sola per dispositivo).';
    const reopen = "Tocca <b>L'ho installata — ricontrolla</b>: la pagina si ricarica e " +
      "questo pannello ti dice se ha funzionato.";
    const install = {
      android: "Apri <b>Impostazioni → Sicurezza → Altro → Crittografia e credenziali → " +
        "Installa un certificato → Certificato CA</b>, poi scegli il file appena " +
        "scaricato. Android ti avvertirà che qualcuno potrebbe monitorare la rete — quel " +
        "qualcuno è il tuo server, vedi la nota qui sotto.",
      ios: "Apri il file scaricato, poi <b>Impostazioni → Profilo scaricato → " +
        "Installa</b>. Poi — questa seconda parte è facile da saltare e senza non " +
        "funziona niente — <b>Impostazioni → Generali → Info → Impostazioni " +
        "certificati</b> e attiva <b>Vivavoce Local CA</b>.",
      windows: "Doppio clic su <b>ca.pem</b> → <b>Installa certificato</b> → " +
        "<b>Computer locale</b> → mettilo in <b>Autorità di certificazione radice " +
        "attendibili</b> (non la scelta automatica, che lo mette nell'archivio sbagliato).",
      macos: "Doppio clic su <b>ca.pem</b> per aprire Accesso Portachiavi, poi trova " +
        "<b>Vivavoce Local CA</b>, aprila e sotto <b>Fidati</b> scegli " +
        "<b>Fidati sempre</b>.",
      other: "Aggiungi <b>ca.pem</b> alle radici attendibili del sistema (sulla maggior " +
        "parte dei desktop Linux: copiala in <code>/usr/local/share/ca-certificates/</code> " +
        "come <code>.crt</code> ed esegui <code>sudo update-ca-certificates</code>). " +
        "Firefox e Chrome possono avere ciascuno il proprio archivio.",
    };
    return [download, install[p] || install.other, reopen];
  },
  ks_chip: "🧒 kid-safe attivo",
  ks_pin_lbl: "PIN kid-safe",
  ks_add_lbl: "Termine da bloccare",
  ks_add: "Blocca",
  ks_lock: "🔒 Richiudi",
  ks_disable: "Disattiva",
  ks_pitch: "<b>🧒 Kid-safe</b> — blocca brani o artisti: le richieste bloccate vengono " +
    "rifiutate su ogni dispositivo, anche a voce («blocca …», «sblocca …»). Protetto da PIN.",
  ks_pin_new_ph: "scegli un PIN (min 6)",
  ks_pin_ph: "PIN",
  ks_enable_btn: "Attiva",
  ks_unlock_btn: "Sblocca",
  ks_locked_line: "<b>🧒 Kid-safe attivo.</b> Inserisci il PIN per modificare la lista.",
  ks_open_line: "<b>🧒 Kid-safe attivo</b> — sbloccato su questo dispositivo. Tocca un termine per sbloccarlo.",
  ks_empty: "Nessun termine bloccato, per ora.",
  ks_wrong_pin: "PIN errato (dopo 5 tentativi l'attesa raddoppia ogni volta).",
  ks_pin_short: "PIN troppo corto: almeno 6 caratteri.",
  ks_locked_out: (s) => "Troppi PIN sbagliati: riprova tra " + s + " s.",
  ks_revoked_note: "Licenza non attiva: la lista resta applicata, ma le modifiche sono bloccate.",
  report_btn: "🚩 Segnala frase incompresa",
  report_title: (t) => "Frase incompresa: «" + t + "»",
  report_body: (r) => "**Frase:** «" + r.text + "»\n" +
    "**Lingua:** " + r.lang + "\n**Sorgente:** " + r.source + "\n" +
    "**Versione:** " + r.version + "\n\n**Cosa doveva succedere:** (scrivilo qui)\n",
  report_saved: "Salvata su questo dispositivo. Si è aperta una issue GitHub " +
    "precompilata: rileggila e premi Submit se vuoi inviarla — niente parte da solo.",
};
