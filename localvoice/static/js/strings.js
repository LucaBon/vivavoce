// The UI string tables: English, and the Italian counterparts of everything
// the markup cannot carry.
//
// Split out of i18n.js when the two tables pushed that file past the repo's
// 400-line limit (tests/test_packaging.py). The seam is real rather than
// arithmetic: this file is data — no DOM, no state, no imports — while
// i18n.js is the machinery that chooses between the two and applies the
// result to the page.
//
// The Italian *labels* are not here: they live in the markup and are
// snapshotted at load (see initI18n), so index.html stays readable as Italian
// HTML. What is here is every string built at runtime, plus the English side
// of the labels.

export const UI_EN = {
  h1: "Vivavoce — local voice control",
  hint_sources: 'It searches <b>your library</b> and <b>streaming</b> on its own. ' +
    'To force a source: “<i>from my music</i> …”, “<i>on tidal</i> …” or “<i>on qobuz</i> …”.',
  send: "Send",
  autosend: "send right after the mic (hands-free)",
  lbl_reclang: "Language I speak to the mic",
  lbl_source: "Music source",
  lbl_player: "Where the music plays",
  wakemode_lbl: "voice-activate with a keyword",
  wakeword_lbl: "keyword to say:",
  wakehint: 'Continuous listening: the microphone stays on and the audio goes through ' +
    'the browser’s speech recognition. Tap the mic once, then say ' +
    '“<b><span id="wwlabel">vivavoce</span></b> …” followed by the command. ' +
    'Either <b>all in one sentence</b>, or say just the keyword, wait to be asked ' +
    'for the command, and then say it. ' +
    '<span class="warn">On Android the browser plays a sound every time listening restarts ' +
    '(every few seconds) and it cannot be silenced from here: on phones, leave this off and ' +
    'use tap-to-talk (one sound per command). The keyword works best on PC/tablet with ' +
    'Chrome.</span>',
  wakehint_server: 'Continuous listening without the beep: the server does the wake-word ' +
    'detection, and the browser only takes the microphone for the command itself. It works ' +
    'in <b>two steps</b>: say “<b><span id="wwlabel_srv">Hey Jarvis</span></b>”, ' +
    '<b>wait for the beep</b>, then say the command. The activation phrase is fixed and ' +
    'English, decided by the model on the server: it cannot be customized. The free-text ' +
    'keyword comes back with the other engine.',
  localasr_lbl: "🎙 local speech recognition (Whisper on the server: audio never leaves home)",
  serverwake_lbl: "🔈 detect the wake word on the server (no Android beep; fixed " +
    "“Hey Jarvis” phrase, in English)",
  readback_lbl: "🔊 read the reply aloud",
  voices_summary: "Voices &amp; languages",
  lbl_foreign: "Default language for foreign titles",
  testvoice: "Test the voices",
  voices_hint: "The reply frame (“Playing …”) is read in your language; the " +
    "title and artist in theirs. Available voices depend on the device.",
  say_summary: "What can I say",
  say_list: "<li>“play Comfortably Numb by Pink Floyd”</li>" +
    "<li>“play the album The Wall” · “play music by Aerosmith”</li>" +
    "<li>“which albums do I have by Yes” → “play number 2” (or “play Fragile”)</li>" +
    "<li>“from my music play …” · “on tidal play …” · “on qobuz play …”</li>" +
    "<li>“pause” · “resume” · “next” · “volume up” · “what's playing”</li>" +
    "<li>“stop in 30 minutes” · “cancel the timer” · “play … in the kitchen”</li>" +
    "<li>“add … to the queue” · “play … next” · “what's in the queue” · “clear the queue”</li>" +
    "<li>“play my favorites” · “play the radio …”</li>",
  tip_names: "Tip: if a name is <b>misheard</b>, fix it in the box and press Send.",
  install_summary: "Install as an app (no certificate warnings)",
  install_steps: '<li>Download the local CA: <a id="calink" href="/ca.pem">ca.pem</a> (once per device).</li>' +
    "<li><b>Android</b>: Settings → Security → More / Encryption &amp; credentials → " +
    "Install a certificate → <b>CA certificate</b> → pick the downloaded file.<br>" +
    "<b>iPhone/iPad</b>: open the file → Settings → Downloaded profile → Install; then " +
    "Settings → General → About → Certificate Trust Settings → enable trust.<br>" +
    "<b>PC</b>: double-click ca.pem → install into “Trusted Root Certification Authorities” " +
    "(Windows) or the Keychain (macOS).</li>" +
    "<li>Reopen this page: green padlock, no more warnings. Now from the browser menu choose " +
    "<b>Install app</b> / <b>Add to Home Screen</b>: it opens full-screen like a real app.</li>",
  install_ca_note: "The CA is generated in your home and signs only this server: it doesn't " +
    "give anyone else a way to intercept your traffic.",
  material_link: "Want to browse queue and covers? Open Material Skin ↗",
  micstate_idle: "tap and speak",
  empty_title: "Try saying or typing:",
  empty_chips: '<button class="choice" data-cmd="play Comfortably Numb by Pink Floyd">play Comfortably Numb by Pink Floyd</button>' +
    '<button class="choice" data-cmd="which albums do I have by Pink Floyd">which albums do I have by Pink Floyd</button>' +
    '<button class="choice" data-cmd="what\'s playing">what\'s playing</button>',
  settings_summary: "Settings",
  // dynamic strings used from JS
  micstate_listening: "listening…",
  no_voice: "(no voice)",
  ph_text: "e.g. play Time by Pink Floyd",
  mic_title: "Tap and speak",
  title_page: "Vivavoce — local voice",
  status_tap_write: "Tap the microphone and speak, or type below.",
  // Art. 50(1) AI Act. `ai_notice` is the English side of the label that lives
  // in the markup; `ai_notice_spoken` is said out loud once per voice session,
  // for the hands-free case where nobody ever looks at the screen.
  ai_notice: "Automated assistant: you are talking to software, not to a person.",
  ai_notice_spoken: "Vivavoce, automated voice assistant.",
  src_auto: "Automatic: library, then streaming",
  src_local: "My library only",
  src_only: "Only ",
  lms_down: "Can't reach the music server (LMS): check that it's on.",
  offline: "This device is offline: check its Wi-Fi.",
  net_error: "Network error talking to the local server.",
  no_mic: "This browser doesn't support the microphone. Use the text box, or open in Chrome/Edge.",
  need_https: "The microphone needs HTTPS when opened from another device. Start the server " +
    "with a certificate (see README) or use the text box.",
  check_text: "Check the text (watch out for names) and press Send.",
  listening: "Listening…",
  listening_wake: (w) => "Listening… say “" + w + " …”",
  say_command: "Yes? Tell me the command…",
  tap_mic: "Tap the microphone and speak.",
  tap_to_resume: "Listening stopped — tap the microphone to resume.",
  wake_gave_up: (e) => "Continuous listening stopped (" + e +
    "). Check the microphone and the connection, then tap to start again.",
  mic_error: "Microphone error: ",
  cmd_timeout: "No answer from the server. Is it still running?",
  still_working: "Still working on the previous command\u2026",
  asr_working: "Transcribing…",
  asr_failed: "Local recognition failed: using the browser's.",
  lbl_text: "Text command",
  log_label: "Command history",
  np_label: "Now playing",
  np_prev: "Previous track",
  np_toggle: "Play/pause",
  np_next: "Next track",
  np_seek: "Track position",
  np_vol: "Volume",
  pro_activate: "Activate",
  pro_key_lbl: "Pro license key",
  pro_buy: "Buy the Pro license ↗",
  pro_pitch: "Microphone, wake word, read-back voices, multi-room and kid-safe " +
    "are <b>Pro</b> features — a one-time license, yours forever. " +
    "Typing commands is free, always.",
  pro_active: (k) => "Pro active — license " + k + ". Thank you for supporting the project!",
  pro_revoked: "This license was <b>disabled or refunded</b>: Pro features are off. " +
    "Enter a valid key to re-activate.",
  pro_err_network: "Couldn't reach the license server. Check the connection and try again.",
  pro_err_invalid: "Key not valid (or activation limit reached): ",
  pro_only: " — Pro feature",
  pro_trial: (n) => "<b>Pro trial — " + (n === 1 ? "last day" : n + " days left") +
    ".</b> Everything is on, microphone included. When it ends, typed commands " +
    "keep working exactly as they do now: nothing breaks, nothing is deleted.",
  pro_trial_over: "<b>Your Pro trial has ended.</b> Typing commands is free, always — " +
    "the microphone, wake word, read-back voices, multi-room and kid-safe come back " +
    "with a one-time license, yours forever.",
  upsell_spoken_trial: (n) => "👆 You could have just said that. Tap the microphone " +
    "and try it — the Pro trial is on for " + (n === 1 ? "one more day" : n + " more days") + ".",
  upsell_spoken_over: "👆 You could have just said that out loud. The microphone is a " +
    "Pro feature — typing stays free.",
  upsell_see_pro: "See Pro",
  cert_state_ok: "<b>✅ Certificate installed.</b> Green padlock, no warnings, and the " +
    "app can be installed from the browser menu (<b>Install app</b> / <b>Add to Home " +
    "Screen</b>).",
  cert_state_untrusted: "<b>⚠️ This device does not trust the certificate yet.</b> " +
    "That is the warning you clicked through to get here — and it is why the microphone " +
    "and the app install are blocked. Two steps, once per device:",
  cert_state_nocert: "<b>⚠️ This device does not trust the certificate</b>, and this " +
    "server offers no local CA to install. Either it uses your own certificate, or it was " +
    "started without <code>tools/make_cert.py</code> — see DEPLOY.md.",
  cert_state_http: "<b>This page is served over plain HTTP.</b> From another device the " +
    "microphone cannot work at all — no certificate installed here would change that: the " +
    "server has to serve HTTPS first (see DEPLOY.md). Typed commands work as they are.",
  cert_state_local: "<b>You are on the computer running the server</b>, so nothing needs " +
    "installing: the microphone already works here. It is opening the page from a <i>phone</i> " +
    "that needs HTTPS and this certificate.",
  cert_state_unknown: "This browser cannot confirm the certificate by itself. If the " +
    "address bar shows a warning instead of a padlock, these steps fix it:",
  cert_verify_btn: "I installed it — check again",
  cert_other_btn: "Another device?",
  cert_other_hide: "Hide the other devices",
  cert_steps: (p) => {
    const download = 'Download the local CA: <a href="/ca.pem" download>ca.pem</a> ' +
      '(once per device).';
    const reopen = "Tap <b>I installed it — check again</b>: the page reloads and this " +
      "panel tells you whether it worked.";
    const install = {
      android: "Open <b>Settings → Security → More → Encryption &amp; credentials → " +
        "Install a certificate → CA certificate</b>, then pick the file you just " +
        "downloaded. Android will warn you that someone could monitor the network — that " +
        "someone is your own server, see the note below.",
      ios: "Open the downloaded file, then <b>Settings → Profile Downloaded → Install</b>. " +
        "Then — this second part is easy to miss and nothing works without it — " +
        "<b>Settings → General → About → Certificate Trust Settings</b> and switch " +
        "<b>Vivavoce Local CA</b> on.",
      windows: "Double-click <b>ca.pem</b> → <b>Install Certificate</b> → " +
        "<b>Local Machine</b> → place it in <b>Trusted Root Certification Authorities</b> " +
        "(not the automatic choice, which puts it in the wrong store).",
      macos: "Double-click <b>ca.pem</b> to open Keychain Access, then find " +
        "<b>Vivavoce Local CA</b>, open it, and under <b>Trust</b> set " +
        "<b>Always Trust</b>.",
      other: "Add <b>ca.pem</b> to your system's trusted root certificates (on most Linux " +
        "desktops: copy it into <code>/usr/local/share/ca-certificates/</code> as a " +
        "<code>.crt</code> and run <code>sudo update-ca-certificates</code>). Firefox and " +
        "Chrome may each keep their own store.",
    };
    return [download, install[p] || install.other, reopen];
  },
  ks_chip: "🧒 kid-safe on",
  ks_pin_lbl: "Kid-safe PIN",
  ks_add_lbl: "Term to block",
  ks_add: "Block",
  ks_lock: "🔒 Re-lock",
  ks_disable: "Turn off",
  ks_pitch: "<b>🧒 Kid-safe</b> — block songs or artists: blocked requests are refused " +
    "on every device, by voice too (“block …”, “unblock …”). PIN-protected.",
  ks_pin_new_ph: "choose a PIN (min 6)",
  ks_pin_ph: "PIN",
  ks_enable_btn: "Enable",
  ks_unlock_btn: "Unlock",
  ks_locked_line: "<b>🧒 Kid-safe on.</b> Enter the PIN to edit the list.",
  ks_open_line: "<b>🧒 Kid-safe on</b> — unlocked on this device. Tap a term to unblock it.",
  ks_empty: "No blocked terms yet.",
  ks_wrong_pin: "Wrong PIN (after 5 tries the wait doubles each time).",
  ks_pin_short: "PIN too short: at least 6 characters.",
  ks_locked_out: (s) => "Too many wrong PINs: try again in " + s + " s.",
  ks_revoked_note: "License not active: the blocklist keeps being enforced, but " +
    "changes are locked.",
  report_btn: "🚩 Report this phrase",
  report_title: (t) => 'Misunderstood phrase: "' + t + '"',
  report_body: (r) => "**Phrase:** “" + r.text + "”\n" +
    "**Language:** " + r.lang + "\n**Source:** " + r.source + "\n" +
    "**Version:** " + r.version + "\n\n**What should have happened:** (write it here)\n",
  report_saved: "Saved on this device. A pre-filled GitHub issue just opened: " +
    "review it and press Submit if you want to send it — nothing is sent by itself.",
};
// Italian counterparts of the dynamic strings (the labels come from the markup).
export const UI_IT = {
  micstate_idle: "tocca e parla",
  micstate_listening: "in ascolto…",
  no_voice: "(nessuna voce)",
  ph_text: "es. riproduci Time dei Pink Floyd",
  mic_title: "Tieni premuto o clicca e parla",
  title_page: "Vivavoce — voce locale",
  status_tap_write: "Tocca il microfono e parla, oppure scrivi qui sotto.",
  // Only the spoken half: the on-screen line is Italian markup already.
  ai_notice_spoken: "Vivavoce, assistente vocale automatico.",
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
  say_command: "Sì? Dimmi il comando…",
  tap_mic: "Tocca il microfono e parla.",
  tap_to_resume: "Ascolto interrotto \u2014 tocca il microfono per riprendere.",
  wake_gave_up: (e) => "Ascolto continuo interrotto (" + e +
    "). Controlla microfono e connessione, poi tocca per ricominciare.",
  mic_error: "Errore microfono: ",
  cmd_timeout: "Nessuna risposta dal server. \u00c8 ancora acceso?",
  still_working: "Sto ancora eseguendo il comando precedente\u2026",
  asr_working: "Trascrivo…",
  asr_failed: "Riconoscimento locale non riuscito: uso quello del browser.",
  lbl_text: "Comando testuale",
  log_label: "Cronologia comandi",
  np_label: "In riproduzione",
  np_prev: "Brano precedente",
  np_toggle: "Riproduci/pausa",
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
