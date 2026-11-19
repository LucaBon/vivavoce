// UI language and status line. The Italian labels live in the markup
// (snapshotted at startup); UI_EN holds the English versions. The page
// language follows the mic-language selector: Italian stays Italian, every
// other speech language gets English.
//
// German is the case that shows what this means: the router understands and
// answers in German (localvoice/lang/de.py), while the page chrome around it
// is English. The two are separate on purpose — a UI catalog is a third set
// of strings to keep in step, and the voice is what the product is.
//
// applyUI() re-renders panels owned by other modules (source selector, voice
// pickers, Pro panel, kid-safe). Those are injected once via setUIHooks() from
// app.js instead of imported, so this module sits at the bottom of the import
// graph and no cycle can bite at evaluation time.

import { $ } from "./util.js";
import { UI_EN, UI_IT } from "./strings.js";

export const LANGS = {
  it: { name: "Italiano", tag: "it-IT" },
  en: { name: "English",  tag: "en-US" },
  es: { name: "Español",  tag: "es-ES" },
  fr: { name: "Français", tag: "fr-FR" },
  de: { name: "Deutsch",  tag: "de-DE" },
};

export const recLang = () => localStorage.getItem("reclang") || "it";
export const foreignDefault = () => localStorage.getItem("foreign_default") || "en";

// The language the SERVER answers in, which is not the mic language whenever
// the mic language has no catalog behind it — none today, and the list below
// is injected so that stays true without an edit here — and is not the page
// language ever, since the chrome is Italian or English only. Read-back needs
// this one: the frame of the reply is written in it, so it has to be spoken by
// its voice. The list is injected by the server — see http_api.REPLY_LANGS.
// The "it" here is not this module's decision: it mirrors
// engine/messages.DEFAULT_LANG, which is what set_lang() actually falls back
// to. The LIST is injected so a fourth catalog needs no edit; the default is
// not, because changing it is a product decision and not a new language.
const REPLY_LANGS = (window.VIVAVOCE_CFG || {}).langs || ["it"];
export const replyLang = () =>
  (REPLY_LANGS.includes(recLang()) ? recLang() : "it");


const IT_MARKUP = {};  // Italian innerHTML of every [data-i18n], snapshotted at load
export const uiLang = () => (recLang() === "it" ? "it" : "en");
export const ui = (key) => (uiLang() === "it" ? UI_IT : UI_EN)[key];

// The base state of the status line, re-rendered on language change. The mic
// handlers overwrite it with transient text; that's fine until the next render.
let statusBase = "default";  // "default" | "nomic" | "nohttps" | "lmsdown" | "offline" | "serverdown"
export const getStatusBase = () => statusBase;
export const setStatusBase = (v) => { statusBase = v; };

export function refreshStatus() {
  const statusEl = $("status");
  if (statusBase === "nomic" || statusBase === "nohttps") {
    statusEl.innerHTML = '<span class="warn">' +
      ui(statusBase === "nomic" ? "no_mic" : "need_https") + "</span>";
  } else if (statusBase === "lmsdown") {
    statusEl.innerHTML = '<span class="warn">' + ui("lms_down") + "</span>";
  } else if (statusBase === "offline" || statusBase === "serverdown") {
    statusEl.innerHTML = '<span class="warn">' +
      ui(statusBase === "offline" ? "offline" : "server_down") + "</span>";
  } else {
    statusEl.textContent = ui("status_tap_write");
  }
}

// LMS reachability lamp: the header LED turns red and the status line warns.
// Only the "default" status is replaced — mic problems keep their message.
//
// `why` says who is not answering, because each sends the user to a different
// box: "lms" (Vivavoce answered, the LMS behind it did not), "offline" (this
// device has no network) or "server" (Vivavoce itself did not answer — a
// stopped server, or the page opened at an address it no longer serves, e.g.
// https:// from the installed app's cache while it now runs on http://).
// Blaming the LMS for the last one sent people to check a hi-fi that worked.
export function setLmsDown(down, why = "lms") {
  document.body.classList.toggle("lmsdown", down);
  const want = !down ? "default"
    : why === "offline" ? "offline" : why === "server" ? "serverdown" : "lmsdown";
  const replaceable = ["default", "lmsdown", "offline", "serverdown"]
    .includes(statusBase);
  if (replaceable && statusBase !== want) { statusBase = want; refreshStatus(); }
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
  // always the field's (see syncWakeLabel in settings.js).
  hooks.syncWakeLabel();
  hooks.buildSourceOptions();
  hooks.buildVoicePickers();  // re-localizes the "(no voice)" option
  hooks.applyPro();           // re-localizes the Pro panel strings
  hooks.renderKidsafe();      // re-localizes the kid-safe panel
  hooks.renderCertSetup();    // re-localizes the certificate panel, keeping
                              // its live verdict (which no markup snapshot has)
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
