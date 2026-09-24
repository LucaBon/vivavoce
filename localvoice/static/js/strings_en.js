// The English UI string table (the Italian one is strings_it.js).
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
//
// Two files, one per language, since the pair outgrew the 400-line limit a
// second time: the seam is the language, so each table can grow on its own.
//
// One table lives next door: micerrors.js, which turns the browser's own
// error codes into sentences. Same kind of data, but it is keyed by somebody
// else's vocabulary rather than by ours, and it is the only thing here that
// has to be revisited when a browser invents a new code.

import { MIC_WHY_EN, micWhy } from "./micerrors.js";

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
  wakehint_server: 'Continuous listening without the beep: the server does the wake-word detection, and the browser only takes the microphone for the command itself. ' +
    'It works in <b>two steps</b>: say “<b><span id="wwlabel_srv">vivavoce</span></b>”, <b>wait for the beep</b>, then say the command. ' +
    'The phrase is the one above and applies to <b>the whole house</b>, not just this device. ' +
    '<span class="warn">It has to be made of real words: the engine only produces words it knows, so a made-up name never fires. If you type one, it says so instead of accepting it.</span>',
  localasr_lbl: "🎙 local speech recognition (Whisper on the server: audio never leaves home)",
  serverwake_lbl: "🔈 detect the wake word on the server (no Android beep)",
  // The refusal from POST /wakeword/phrase, and the confirmation. A phrase the
  // engine has no pronunciation for does not degrade — it never fires at all —
  // so this is a refusal to state, not a warning to soften.
  wake_phrase_rejected: (words) => `“${words.join("”, “")}”: the server engine has no pronunciation for ` +
    `${words.length > 1 ? "these words" : "this word"}, so it would never hear it. Choose a phrase made of real words.`,
  wake_phrase_saved: "Keyword saved for the whole house.",
  wake_phrase_unverified: "Saved, but not checked against the server engine's vocabulary: if it is not a real word it may never trigger.",
  wake_phrase_failed: (why) => `NOT saved for the house (${why}). This device still answers to it; the others will not.`,
  wake_phrase_save_failed: "NOT saved for the house: the server could not write its data directory. This device still answers to it; the others will not. The server log says which file.",
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
  material_link: "Browse the queue, the covers and the library with Material Skin",
  browse_close: "✕ Back to commands",
  browse_credit: "Material Skin by Craig Drummond ↗",
  micstate_idle: "tap and speak",
  empty_title: "Try saying or typing:",
  empty_chips: '<button class="choice" data-cmd="play Comfortably Numb by Pink Floyd">play Comfortably Numb by Pink Floyd</button>' +
    '<button class="choice" data-cmd="which albums do I have by Pink Floyd">which albums do I have by Pink Floyd</button>' +
    '<button class="choice" data-cmd="what\'s playing">what\'s playing</button>',
  settings_summary: "Settings",
  grp_listen: "Listening",
  grp_music: "Music",
  grp_reply: "Replies",
  grp_pro: "Pro",
  // dynamic strings used from JS
  micstate_listening: "listening…",
  no_voice: "(no voice)",
  ph_text: "e.g. play Time by Pink Floyd",
  mic_title: "Microphone: tap and speak, tap again to stop",
  title_page: "Vivavoce — local voice",
  status_tap_write: "Tap the microphone and speak, or type below.",
  status_locked: "Type your command below, it's free. The microphone is Pro: tap it to learn more.",
  // Art. 50(1) AI Act. `ai_notice` is the English side of the label that lives
  // in the markup; `ai_notice_spoken` is said out loud once per voice session,
  // for the hands-free case where nobody ever looks at the screen.
  //
  // The spoken one deliberately does NOT open with the product name. It used
  // to — "Vivavoce, automated voice assistant." — and the product name is the
  // default wake word, so the app said its own wake word through the
  // loudspeaker into its own live microphone and took the rest of the
  // sentence for a command. tts.js's echo gate is the general fix; this is
  // simply not handing it the one collision that ships by default.
  ai_notice: "Automated assistant: you are talking to software, not to a person.",
  ai_notice_spoken: "Automated voice assistant.",
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
  wake_gave_up: (e) => "Continuous listening stopped: " + micWhy(MIC_WHY_EN, e) +
    " Tap the microphone to start again.",
  mic_error: (e) => "Microphone: " + micWhy(MIC_WHY_EN, e),
  cmd_timeout: "No answer from the server. Is it still running?",
  still_working: "Still working on the previous command\u2026",
  asr_working: "Transcribing…",
  asr_failed: "Local recognition failed: using the browser's.",
  lbl_controls: "Commands",
  lbl_text: "Text command",
  log_label: "Command history",
  np_label: "Now playing",
  np_prev: "Previous track",
  np_play: "Play",
  np_pause: "Pause",
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
  // The key may have been fine: what failed was writing the activation to
  // disk. Saying "not valid" to somebody who just paid is the worst answer.
  // Not "try again": activate() registers the instance with the licence
  // server BEFORE writing to disk, so each retry spends another seat and
  // walks the customer into the activation limit.
  pro_err_save: "Activated \u2014 but it could not be saved on this machine. Free some disk space and reload the page; the key is already registered, so do not enter it again.",
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
