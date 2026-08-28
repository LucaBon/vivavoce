// The chat log and the /api/v1/command round-trip: bubbles, the tappable
// "did you mean" choices, and the send pipeline shared by the text box and
// both recognisers (Web Speech and the server's local ASR).

import { $, clientId } from "./util.js";
import { ui, recLang, getStatusBase } from "./i18n.js";
import { currentSource, currentPlayer } from "./settings.js";
import { refreshNowPlaying } from "./nowplaying.js";
import { readbackOn, speak } from "./tts.js";
import { trialInfo, isLicensed, showProUpsell } from "./pro.js";

export function bubble(text, who) {
  const log = $("log");
  $("empty").style.display = "none";  // first message replaces the onboarding hints
  const d = document.createElement("div");
  d.className = "bubble " + who;
  d.textContent = text;
  log.prepend(d);
  // The log is a receipt, not an archive: keep the DOM bounded in long
  // sessions (~25 exchanges; choice rows age out with the rest).
  while (log.children.length > 50) log.lastChild.remove();
  log.closest(".content").scrollTop = 0;  // newest bubble always in view
  return d;
}

// --- "Report a misunderstood phrase" (privacy-first) ---
// Offered only when the router matched nothing (data.unmatched). Tapping it
// saves the report locally and opens a pre-filled GitHub issue the user can
// review and submit — nothing ever leaves the device on its own.
const REPORT_ISSUES_URL = "https://github.com/LucaBon/vivavoce/issues/new";
const REPORT_STORE_KEY = "vivavoce_reports";
const REPORT_STORE_MAX = 50;

function saveReport(entry) {
  let list = [];
  try { list = JSON.parse(localStorage.getItem(REPORT_STORE_KEY)) || []; }
  catch (e) { /* corrupt store: start over */ }
  list.push(entry);
  localStorage.setItem(REPORT_STORE_KEY,
                       JSON.stringify(list.slice(-REPORT_STORE_MAX)));
}

function reportUnmatched(text, statusBubble) {
  const entry = { text, lang: recLang(), source: currentSource(),
                  version: (window.VIVAVOCE_CFG || {}).version || "unknown",
                  when: new Date().toISOString() };
  saveReport(entry);
  const url = REPORT_ISSUES_URL
    + "?title=" + encodeURIComponent(ui("report_title")(text))
    + "&body=" + encodeURIComponent(ui("report_body")(entry));
  window.open(url, "_blank", "noopener");
  if (statusBubble) statusBubble.textContent = ui("report_saved");
}

function renderReportButton(afterEl, text) {
  const row = document.createElement("div");
  row.className = "choices";
  const btn = document.createElement("button");
  btn.className = "choice";
  btn.textContent = ui("report_btn");
  btn.onclick = () => {
    const note = document.createElement("div");
    note.className = "bubble sys";
    row.replaceWith(note);
    reportUnmatched(text, note);
  };
  row.appendChild(btn);
  afterEl.after(row);
}

// Render the server's numbered "did you mean" list as tappable buttons just
// under its reply bubble, so on the web app you tap instead of re-speaking
// "metti la 2". The pick reuses the server-side candidate list.
// One per language the router parses; anything else falls back to Italian,
// exactly as the router itself does.
const PICK_PHRASE = {
  it: (n) => "metti la " + n,
  en: (n) => "play number " + n,
  de: (n) => "spiel Nummer " + n,
  fr: (n) => "mets le numéro " + n,
};

function renderChoices(afterEl, choices) {
  const row = document.createElement("div");
  row.className = "choices";
  choices.forEach(c => {
    const btn = document.createElement("button");
    btn.className = "choice";
    btn.textContent = c.n + " · " + c.label;
    // The pick phrase must match the language the SERVER parses (it/en/de/fr;
    // es falls back to Italian patterns), not the page chrome language —
    // which for German is English, and would send a phrase de.py never sees.
    btn.onclick = () => send((PICK_PHRASE[recLang()] || PICK_PHRASE.it)(c.n));
    row.appendChild(btn);
  });
  afterEl.after(row);
}

// --- The in-flow upgrade prompt ---
// The ask used to live in the settings panel, where nobody goes and where
// "buy Pro" is an abstraction. It belongs at the one moment it means
// something concrete: just after a command the user TYPED, which they could
// have simply said. Two rules keep it a hint rather than nagging — never
// before the third day, and at most once per page session.
const PROMPT_FIRST_DAY = 3;
let promptedThisSession = false;

function micIsUsableHere() {
  // No point advertising a button that cannot work: a browser with no speech
  // recognition, or a page served over plain HTTP from another device, says
  // so in the status line already.
  const base = getStatusBase();
  return base !== "nomic" && base !== "nohttps";
}

function maybePromptSpoken(afterEl) {
  if (promptedThisSession || isLicensed() || !micIsUsableHere()) return;
  const trial = trialInfo();
  if (!trial || trial.day < PROMPT_FIRST_DAY) return;
  promptedThisSession = true;
  const note = document.createElement("div");
  note.className = "bubble sys upsell";
  note.innerHTML = trial.active ? ui("upsell_spoken_trial")(trial.days_left)
                                : ui("upsell_spoken_over");
  afterEl.after(note);
  if (trial.active) return;  // the mic is right there; nothing to sell yet
  const row = document.createElement("div");
  row.className = "choices";
  const btn = document.createElement("button");
  btn.className = "choice";
  btn.textContent = ui("upsell_see_pro");
  btn.onclick = showProUpsell;
  row.appendChild(btn);
  note.after(row);
}

// An /api/v1/command round-trip is a couple of LMS calls; anything past this
// is the server being gone, not slow. Without a deadline `sending` never
// cleared and the whole session went quiet: every later voice command was
// beeped at, then dropped on the `sending` guard with nothing on screen to
// explain it.
const COMMAND_TIMEOUT_MS = 15000;

let sending = false;
/** Is a command in flight? The wake path checks this before beeping. */
export const isSending = () => sending;
export async function send(text, alternatives, opts) {
  text = (text || "").trim();
  if (!text || sending) return;  // one in-flight command at a time
  sending = true;
  bubble(text, "you");
  // Placeholder bubble with animated dots while the LMS query runs; it is
  // converted in place into the reply (or the error) when the fetch settles.
  const p = bubble("", "sys pending");
  p.setAttribute("aria-hidden", "true");
  $("send").disabled = true;
  // lang: the mic-language selector — the server parses the command and
  // replies in that language (it/en; others fall back to Italian).
  const body = { text, client: clientId(), source: currentSource(),
                 lang: recLang(), player: currentPlayer() };
  if (alternatives && alternatives.length > 1) body.alternatives = alternatives;
  try {
    const r = await fetch("/api/v1/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout
        ? AbortSignal.timeout(COMMAND_TIMEOUT_MS) : undefined
    });
    const data = await r.json();
    // If the server kept a different alternative than what we heard first,
    // show it in the box so the next correction starts from what worked.
    if (data.used && data.used.trim() && data.used.trim() !== text) {
      $("text").value = data.used;
    }
    p.classList.remove("pending");
    p.removeAttribute("aria-hidden");
    if (data.ok === false) p.classList.add("warn");
    p.textContent = data.speech;
    if (Array.isArray(data.choices) && data.choices.length) renderChoices(p, data.choices);
    // Parser gap (nothing matched): offer the local, user-initiated report.
    if (data.unmatched) renderReportButton(p, (data.used || text));
    // Only when it worked: an upgrade pitch stapled to a failure reads as
    // "pay us and maybe it will understand you", which is not the offer.
    if (data.ok !== false && !data.unmatched && opts && opts.typed) {
      maybePromptSpoken(p);
    }
    if (readbackOn()) speak(data.speech, data.terms);
    // A play/skip command changes the track: don't wait for the next poll.
    setTimeout(refreshNowPlaying, 800);
  } catch (e) {
    // Whatever went wrong, the pending bubble must stop pretending: it is
    // the only thing on screen saying a command is still being worked on.
    p.classList.remove("pending");
    p.removeAttribute("aria-hidden");
    p.classList.add("warn");
    p.textContent = (e && (e.name === "TimeoutError" || e.name === "AbortError"))
      ? ui("cmd_timeout") : ui("net_error");
  } finally {
    sending = false;
    $("send").disabled = false;
  }
}

// Shared by both recognisers (Web Speech and local): put the transcript in
// the box and either send right away (hands-free) or wait for a check.
export function runCommand(txt, alts) {
  $("text").value = txt;
  send(txt, alts);
  $("text").value = "";
}
// --- "send right after the mic" ---
// Persisted like every other toggle in the panel (it wasn't: it reset to off
// on every reload, so hands-free had to be re-armed by hand each time the app
// was opened), and until the user has an opinion it FOLLOWS wake mode —
// continuous listening whose transcript then sits in a box waiting for a tap
// isn't hands-free at all, and you're across the room. Touching the checkbox
// once records a choice that is then honoured for good, in both directions.
const AUTOSEND_KEY = "autosend";
const autosendChosen = () => localStorage.getItem(AUTOSEND_KEY) !== null;
export const autosendOn = () => $("autosend").checked;
export function autosendFollowWakeMode(wakeOn) {
  if (!autosendChosen()) $("autosend").checked = wakeOn;
}

// Is the last transcript sitting in the box waiting for Send, rather than
// having been sent? Whoever closes a capture has to ask: "check the text and
// press Send" is a question, and answering it with "tap the microphone" — as
// the end of the capture used to, immediately — describes a box silently
// waiting for Send as if nothing were waiting at all. The wake path has the
// same rule, in its own handler (wakeword.js).
let awaitingReview = false;
export const isAwaitingReview = () => awaitingReview;
/** A capture has started: whatever is in the box is no longer the answer. */
export function clearAwaitingReview() { awaitingReview = false; }

export function handleManualFinal(txt, alts) {
  $("text").value = txt;
  awaitingReview = !$("autosend").checked;
  if ($("autosend").checked) { runCommand(txt, alts); }
  else { $("status").textContent = ui("check_text"); $("text").focus(); }
}

export function initChat() {
  // Tappable example commands in the empty state. Delegated so the handler
  // survives the innerHTML swap done by applyUI() on language change.
  $("empty").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cmd]");
    if (btn) send(btn.dataset.cmd, null, { typed: true });
  });

  // Read from the wake-mode key directly rather than the checkbox: initChat()
  // runs before initMic() restores it, and both read the same stored value.
  $("autosend").checked = autosendChosen()
    ? localStorage.getItem(AUTOSEND_KEY) === "1"
    : localStorage.getItem("wakemode") === "1";
  $("autosend").onchange = () =>
    localStorage.setItem(AUTOSEND_KEY, $("autosend").checked ? "1" : "0");

  const sendTyped = () => {
    send($("text").value, null, { typed: true });
    $("text").value = "";
  };
  $("send").onclick = sendTyped;
  $("text").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendTyped();
  });
}
