// UI language and status line. The Italian labels live in the markup
// (snapshotted at startup); UI_EN holds the English versions. The page
// language follows the mic-language selector: Italian stays Italian, every
// other speech language gets English.
//
// applyUI() re-renders panels owned by other modules (source selector, voice
// pickers, Pro panel, kid-safe). Those are injected once via setUIHooks() from
// app.js instead of imported, so this module sits at the bottom of the import
// graph and no cycle can bite at evaluation time.

import { $ } from "./util.js";

export const LANGS = {
  it: { name: "Italiano", tag: "it-IT" },
  en: { name: "English",  tag: "en-US" },
  es: { name: "Español",  tag: "es-ES" },
  fr: { name: "Français", tag: "fr-FR" },
  de: { name: "Deutsch",  tag: "de-DE" },
};

export const recLang = () => localStorage.getItem("reclang") || "it";
export const foreignDefault = () => localStorage.getItem("foreign_default") || "en";

const UI_EN = {
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
  src_auto: "Automatic: library, then streaming",
  src_local: "My library only",
  src_only: "Only ",
  lms_down: "Can't reach the music server (LMS): check that it's on.",
  net_error: "Network error talking to the local server.",
  no_mic: "This browser doesn't support the microphone. Use the text box, or open in Chrome/Edge.",
  need_https: "The microphone needs HTTPS when opened from another device. Start the server " +
    "with a certificate (see README) or use the text box.",
  check_text: "Check the text (watch out for names) and press Send.",
  listening: "Listening…",
  listening_wake: (w) => "Listening… say “" + w + " …”",
  say_command: "Yes? Tell me the command…",
  tap_mic: "Tap the microphone and speak.",
  mic_error: "Microphone error: ",
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
  ks_chip: "🧒 kid-safe on",
  ks_pin_lbl: "Kid-safe PIN",
  ks_add_lbl: "Term to block",
  ks_add: "Block",
  ks_lock: "🔒 Re-lock",
  ks_disable: "Turn off",
  ks_pitch: "<b>🧒 Kid-safe</b> — block songs or artists: blocked requests are refused " +
    "on every device, by voice too (“block …”, “unblock …”). PIN-protected.",
  ks_pin_new_ph: "choose a PIN (min 4)",
  ks_pin_ph: "PIN",
  ks_enable_btn: "Enable",
  ks_unlock_btn: "Unlock",
  ks_locked_line: "<b>🧒 Kid-safe on.</b> Enter the PIN to edit the list.",
  ks_open_line: "<b>🧒 Kid-safe on</b> — unlocked on this device. Tap a term to unblock it.",
  ks_empty: "No blocked terms yet.",
  ks_wrong_pin: "Wrong PIN (after 5 tries, wait a minute).",
  ks_pin_short: "PIN too short: at least 4 characters.",
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
const UI_IT = {
  micstate_idle: "tocca e parla",
  micstate_listening: "in ascolto…",
  no_voice: "(nessuna voce)",
  ph_text: "es. riproduci Time dei Pink Floyd",
  mic_title: "Tieni premuto o clicca e parla",
  title_page: "Vivavoce — voce locale",
  status_tap_write: "Tocca il microfono e parla, oppure scrivi qui sotto.",
  src_auto: "Automatica: libreria, poi streaming",
  src_local: "Solo la mia libreria",
  src_only: "Solo ",
  lms_down: "Non raggiungo il server musicale (LMS): controlla che sia acceso.",
  net_error: "Errore di rete verso il server locale.",
  no_mic: "Questo browser non supporta il microfono. Usa la casella di testo, oppure apri con Chrome/Edge.",
  need_https: "Il microfono richiede HTTPS quando apri da un altro dispositivo. Avvia il " +
    "server con un certificato (vedi README) oppure usa la casella di testo.",
  check_text: "Controlla il testo (occhio ai nomi inglesi) e premi Invia.",
  listening: "Ascolto…",
  listening_wake: (w) => "In ascolto… di' «" + w + " …»",
  say_command: "Sì? Dimmi il comando…",
  tap_mic: "Tocca il microfono e parla.",
  mic_error: "Errore microfono: ",
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
  ks_chip: "🧒 kid-safe attivo",
  ks_pin_lbl: "PIN kid-safe",
  ks_add_lbl: "Termine da bloccare",
  ks_add: "Blocca",
  ks_lock: "🔒 Richiudi",
  ks_disable: "Disattiva",
  ks_pitch: "<b>🧒 Kid-safe</b> — blocca brani o artisti: le richieste bloccate vengono " +
    "rifiutate su ogni dispositivo, anche a voce («blocca …», «sblocca …»). Protetto da PIN.",
  ks_pin_new_ph: "scegli un PIN (min 4)",
  ks_pin_ph: "PIN",
  ks_enable_btn: "Attiva",
  ks_unlock_btn: "Sblocca",
  ks_locked_line: "<b>🧒 Kid-safe attivo.</b> Inserisci il PIN per modificare la lista.",
  ks_open_line: "<b>🧒 Kid-safe attivo</b> — sbloccato su questo dispositivo. Tocca un termine per sbloccarlo.",
  ks_empty: "Nessun termine bloccato, per ora.",
  ks_wrong_pin: "PIN errato (dopo 5 tentativi, aspetta un minuto).",
  ks_pin_short: "PIN troppo corto: almeno 4 caratteri.",
  ks_revoked_note: "Licenza non attiva: la lista resta applicata, ma le modifiche sono bloccate.",
  report_btn: "🚩 Segnala frase incompresa",
  report_title: (t) => "Frase incompresa: «" + t + "»",
  report_body: (r) => "**Frase:** «" + r.text + "»\n" +
    "**Lingua:** " + r.lang + "\n**Sorgente:** " + r.source + "\n" +
    "**Versione:** " + r.version + "\n\n**Cosa doveva succedere:** (scrivilo qui)\n",
  report_saved: "Salvata su questo dispositivo. Si è aperta una issue GitHub " +
    "precompilata: rileggila e premi Submit se vuoi inviarla — niente parte da solo.",
};

const IT_MARKUP = {};  // Italian innerHTML of every [data-i18n], snapshotted at load
export const uiLang = () => (recLang() === "it" ? "it" : "en");
export const ui = (key) => (uiLang() === "it" ? UI_IT : UI_EN)[key];

// The base state of the status line, re-rendered on language change. The mic
// handlers overwrite it with transient text; that's fine until the next render.
let statusBase = "default";  // "default" | "nomic" | "nohttps" | "lmsdown"
export const getStatusBase = () => statusBase;
export const setStatusBase = (v) => { statusBase = v; };

export function refreshStatus() {
  const statusEl = $("status");
  if (statusBase === "nomic" || statusBase === "nohttps") {
    statusEl.innerHTML = '<span class="warn">' +
      ui(statusBase === "nomic" ? "no_mic" : "need_https") + "</span>";
  } else if (statusBase === "lmsdown") {
    statusEl.innerHTML = '<span class="warn">' + ui("lms_down") + "</span>";
  } else {
    statusEl.textContent = ui("status_tap_write");
  }
}

// LMS reachability lamp: the header LED turns red and the status line warns.
// Only the "default" status is replaced — mic problems keep their message.
export function setLmsDown(down) {
  document.body.classList.toggle("lmsdown", down);
  if (down && statusBase === "default") { statusBase = "lmsdown"; refreshStatus(); }
  else if (!down && statusBase === "lmsdown") { statusBase = "default"; refreshStatus(); }
}

// Renderers owned by other modules, injected once from app.js (see above).
let hooks = {};
export function setUIHooks(h) { hooks = h; }

export function applyUI() {
  const en = uiLang() === "en";
  document.documentElement.lang = en ? "en" : "it";
  document.title = ui("title_page");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const k = el.dataset.i18n;
    el.innerHTML = (en && UI_EN[k] !== undefined) ? UI_EN[k] : IT_MARKUP[k];
  });
  $("text").placeholder = ui("ph_text");
  $("text").setAttribute("aria-label", ui("lbl_text"));
  $("mic").title = ui("mic_title");
  $("mic").setAttribute("aria-label", ui("mic_title"));
  $("log").setAttribute("aria-label", ui("log_label"));
  // the data-i18n swap resets #micstate to idle text: keep it truthful while listening
  $("micstate").textContent = $("mic").classList.contains("listening")
    ? ui("micstate_listening") : ui("micstate_idle");
  // wakehint embeds the wake-word span: restore its live value after the
  // swap. Via the hook, not by reading the field — the phrase in use isn't
  // always the field's (see setWakeWordOverride in settings.js).
  hooks.syncWakeLabel();
  hooks.buildSourceOptions();
  hooks.buildVoicePickers();  // re-localizes the "(no voice)" option
  hooks.applyPro();           // re-localizes the Pro panel strings
  hooks.renderKidsafe();      // re-localizes the kid-safe panel
  refreshStatus();
}

// Guess a term's language; proper nouns usually have no signal -> foreign default.
export function detectLang(text) {
  const s = (text || "").toLowerCase();
  if (/[ñ]|¡|¿/.test(s)) return "es";
  if (/ß|[äöü]/.test(s)) return "de";
  if (/[çœâêëîïôû]/.test(s)) return "fr";
  const w = new Set(s.split(/\s+/));
  const any = (arr) => arr.some(x => w.has(x));
  if (any(["der","die","das","und","ich","nicht","ein","mit","für"])) return "de";
  if (any(["le","les","une","des","et","dans","pour","avec","je"])) return "fr";
  if (any(["el","los","las","una","con","por","para","que"])) return "es";
  if (any(["gli","che","della","dei","degli","nella","alla"])) return "it";
  return foreignDefault();
}

// Snapshot the Italian markup before anything rewrites it.
export function initI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    IT_MARKUP[el.dataset.i18n] = el.innerHTML;
  });
}
