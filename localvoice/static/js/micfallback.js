// What the microphone does when the browser's own recogniser cannot reach its
// cloud service.
//
// Edge answers every Web Speech start() with `network` ~0.4 s later, on
// machines where Chrome works fine: the mic lit up and went dark again on every
// tap, and continuous listening gave up after a handful of restarts. Nothing a
// page can do brings that service back, so this module chooses what replaces it:
//
// * tap-to-talk carries on with local recognition (Whisper on the server);
// * continuous listening moves to the server-side wake word (Vosk), and its
//   command capture to local recognition too when the server has it;
// * with neither installed, the page says to use Chrome — and on Android
//   offers to open this very page there, which is as far as a page can go:
//   it can neither start another browser on a PC nor install one.
//
// Split out of mic.js, which sits at the 400-line ceiling the repo sets itself
// (see tests/test_packaging.py); mic.js decides WHEN, this module decides WHAT.

import { $ } from "./util.js";
import { ui, uiLang } from "./i18n.js";
import { localAsrUsable, startLocalRec } from "./localasr.js";
import { serverWakeUsable, syncWakePhrase } from "./miccapture.js";

// `language-not-supported` belongs here too: the browser's service does not
// know the language, Whisper does.
const SERVICE_DOWN = new Set(["network", "language-not-supported"]);
export const serviceDown = (e) => SERVICE_DOWN.has(e && e.error);

function tick(id) {
  $(id).checked = true;
  localStorage.setItem(id, "1");
}

/** Tap-to-talk: the same tap goes on listening, through the server. Ticks
 *  the toggle too, so the next taps skip the broken service altogether. */
export function useLocalAsrInstead() {
  tick("localasr");
  startLocalRec().then(() => {
    if ($("mic").classList.contains("listening")) $("status").textContent = ui("asr_fallback");
  });
}

/** Continuous listening: hand it to the server-side engine. `restart` is
 *  mic.js's restartWakeListening, which stops the browser's recogniser and
 *  starts whichever engine is selected — the server one, once ticked here. */
export function useServerWakeInstead(restart) {
  tick("serverwake");
  // The capture after the trigger would otherwise fall back to Web Speech's
  // one-shot recogniser: the very service that just failed.
  if (localAsrUsable()) tick("localasr");
  syncWakePhrase();
  restart();
}

// Kept here rather than in strings.js, which is at the line ceiling, and
// because it is one panel's worth of words, like micerrors.js.
const HINT = {
  it: { why: "Il riconoscimento vocale di questo browser non funziona qui " +
                "(con Edge succede spesso). In Chrome il microfono funziona:",
        open: "Apri in Chrome", copy: "Copia indirizzo", copied: "Copiato",
        get: "Scarica Chrome" },
  en: { why: "This browser's speech recognition does not work here (Edge " +
             "often fails). The microphone works in Chrome:",
        open: "Open in Chrome", copy: "Copy address", copied: "Copied",
        get: "Get Chrome" },
};

const isAndroid = () => /Android/i.test(navigator.userAgent);

function el(tag, text, attrs) {
  const n = document.createElement(tag);
  if (text) n.textContent = text;
  Object.assign(n, attrs || {});
  return n;
}

/** Say "use Chrome", with the one action each platform allows. */
export function showChromeHint() {
  const box = $("chromehint");
  const t = HINT[uiLang()] || HINT.en;
  box.replaceChildren(el("span", t.why + " "));
  if (isAndroid()) {
    // Chrome's own intent URL: opens this page in Chrome, or the Play Store
    // page for it when it is not installed.
    const scheme = location.protocol.replace(":", "");
    box.append(el("a", t.open, { className: "chromeopen",
      href: "intent://" + location.host + location.pathname +
            "#Intent;scheme=" + scheme + ";package=com.android.chrome;end" }));
  } else {
    box.append(el("code", location.origin + location.pathname), " ");
    const copy = el("button", t.copy, { type: "button" });
    copy.onclick = () => {
      navigator.clipboard.writeText(location.origin + location.pathname)
        .then(() => { copy.textContent = t.copied; }, () => {});
    };
    box.append(copy, " ", el("a", t.get, {
      href: "https://www.google.com/chrome/", target: "_blank", rel: "noopener" }));
  }
  box.hidden = false;
}
