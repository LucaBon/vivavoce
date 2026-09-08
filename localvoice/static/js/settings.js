// Settings panel wiring: wake-word field, music-source selector and the
// player (room) selector. Page-level config the server injects (the streaming
// services actually installed on the LMS) reaches us via window.VIVAVOCE_CFG,
// set by a tiny inline script in index.html so the substitution keeps working
// with the JS served as static files.

import { $ } from "./util.js";
import { ui } from "./i18n.js";
import { isPro, showProUpsell } from "./pro.js";
import { refreshNowPlaying } from "./nowplaying.js";

// --- wake-word field (used by the mic recogniser) ---
export const wakeWord = () => ($("wakeword").value || "vivavoce").trim();

// The phrase continuous listening ACTUALLY answers to. Normally the field
// above — but a FIXED-phrase server engine is locked to its own English model
// phrase ("hey jarvis", see pro/wakeword.py) and cannot hear the free-text
// one at all, so showing "vivavoce" in the hint while that engine is
// selected was simply false: testers read the hint, said "vivavoce", and got
// nothing. The Vosk engine hears the typed phrase, so it sets no override and
// this falls through to the field. miccapture.js pushes the override in
// whenever the engine choice changes.
let wakeOverride = "";
export const activeWakeWord = () => wakeOverride || wakeWord();
export function setWakeWordOverride(phrase) {
  wakeOverride = (phrase || "").trim();
  syncWakeLabel();
}
export function syncWakeLabel() {
  // One span per hint (only one hint is visible at a time, see syncWakePhrase
  // in mic.js): the browser one quotes the field, the server one the model's
  // own phrase. Duplicate ids aren't an option, hence two.
  const label = $("wwlabel");
  if (label) label.textContent = wakeWord();
  const srvLabel = $("wwlabel_srv");
  if (srvLabel && wakeOverride) srvLabel.textContent = wakeOverride;
  // The free-phrase server engine has its own hint, and it quotes the field
  // like the browser one does — there is no override to show there.
  const freeLabel = $("wwlabel_free");
  if (freeLabel) freeLabel.textContent = wakeWord();
  // Greyed out while the override holds: the field configures nothing then,
  // and an editable box next to a phrase it can't change invites the mistake.
  const field = $("wakeword");
  if (field) field.disabled = !!wakeOverride;
}

// --- music source selector (auto / local / streaming services) ---
// The server substitutes __SERVICES__ with the streaming services actually
// available on the LMS, so e.g. Qobuz only shows up when its plugin is there.
const SERVICES = (window.VIVAVOCE_CFG || {}).services || [];
const SERVICE_NAMES = { tidal: "TIDAL", qobuz: "Qobuz" };
export function buildSourceOptions() {
  const sel = $("source");
  const cur = sel.value || localStorage.getItem("source") || "auto";
  const opts = [["auto", ui("src_auto")], ["local", ui("src_local")]]
    .concat(SERVICES.map(s => [s, ui("src_only") + (SERVICE_NAMES[s] || s)]));
  sel.innerHTML = opts.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
  // A saved service that is no longer offered falls back to auto.
  sel.value = opts.some(([v]) => v === cur) ? cur : "auto";
  sel.onchange = () => localStorage.setItem("source", sel.value);
}
export const currentSource = () => $("source").value || "auto";

// --- Player (room) selector — a Pro feature, like its voice form
// («metti … in cucina», both enforced server-side). Filled from /players;
// hidden while the house has a single player; locked (padlock + upsell) on
// the free tier. The choice is per-device (localStorage) and rides along on
// /api/v1/command, /player, /nowplaying — only when Pro, so a stale value is inert.
export const currentPlayer = () => (isPro() ? localStorage.getItem("player") || "" : "");
let PLAYERS = [], PLAYERS_CURRENT = "";
export function renderPlayers() {
  const row = $("playerrow"), sel = $("player");
  if (PLAYERS.length <= 1) { row.style.display = "none"; return; }
  row.style.display = "";
  sel.innerHTML = "";
  PLAYERS.forEach(p => {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.name;
    sel.appendChild(o);
  });
  const cur = currentPlayer();
  sel.value = (cur && PLAYERS.some(p => p.id === cur)) ? cur
            : (PLAYERS_CURRENT || PLAYERS[0].id);
  // NOT `disabled`: a disabled control dispatches no events at all, so the
  // padlock next to it was the one thing on this panel that did nothing when
  // tapped — the gesture that most obviously means "tell me about this".
  // aria-disabled says the same thing to assistive tech, and the handlers
  // below both refuse the change and answer the question.
  sel.setAttribute("aria-disabled", isPro() ? "false" : "true");
  sel.classList.toggle("locked", !isPro());
  $("playerlock").hidden = isPro();
}
// The screenshot harness feeds the selector without a backend.
export function setPlayersData(players, current) {
  PLAYERS = players; PLAYERS_CURRENT = current || "";
}
async function loadPlayers() {
  try {
    const r = await fetch("/players");
    const d = await r.json();
    if (!d.ok || !Array.isArray(d.players)) return;
    PLAYERS = d.players;
    PLAYERS_CURRENT = d.current || "";
    renderPlayers();
  } catch (e) { /* static/offline: the row stays hidden */ }
}

// --- the wake phrase, household-wide ---------------------------------------
// It used to live only in this browser's localStorage, which was enough while
// only this browser could hear it. The server engine listens on behalf of
// every device in the house, so the server holds the answer and localStorage
// becomes the offline fallback — the browser engine still has to work with
// the server unreachable, or a network hiccup would take the microphone with
// it.
const PHRASE_SAVE_DEBOUNCE_MS = 700;
let phraseTimer = null;

function showPhraseMessage(text, bad) {
  const box = $("wakewordmsg");
  if (!box) return;
  box.textContent = text || "";
  box.style.display = text ? "" : "none";
  box.classList.toggle("warn", !!bad);
}

async function savePhrase(phrase) {
  try {
    const r = await fetch("/wakeword/phrase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phrase }),
    });
    const d = await r.json();
    if (d.ok) { showPhraseMessage(ui("wake_phrase_saved"), false); return; }
    if (d.error === "out_of_vocabulary" && (d.words || []).length) {
      // Kept locally on purpose: the BROWSER engine has no lexicon and hears
      // this perfectly well. What is refused is the household-wide setting,
      // and saying which word is the whole value of the refusal.
      showPhraseMessage(ui("wake_phrase_rejected")(d.words), true);
      return;
    }
    // "unavailable" is the ordinary answer on a box without the engine, and
    // there is nothing for the user to do about it: stay quiet.
    showPhraseMessage("", false);
  } catch (e) {
    showPhraseMessage("", false);  // offline: the local value still works
  }
}

async function loadPhrase() {
  try {
    const r = await fetch("/wakeword/phrase");
    const d = await r.json();
    if (!d.ok || !d.phrase) return;
    $("wakeword").value = d.phrase;
    localStorage.setItem("wakeword", d.phrase);
    syncWakeLabel();
  } catch (e) { /* offline: localStorage already filled the field */ }
}

export function initSettings() {
  $("wakeword").value = localStorage.getItem("wakeword") || "vivavoce";
  syncWakeLabel();
  $("wakeword").oninput = () => {
    // Local first and unconditionally: the browser engine answers to this
    // immediately, whatever the server later says about it.
    localStorage.setItem("wakeword", $("wakeword").value);
    syncWakeLabel();
    showPhraseMessage("", false);
    clearTimeout(phraseTimer);
    // Debounced: oninput fires per keystroke, and "v", "vi", "viv" are three
    // phrases the house would each be told to listen for.
    const phrase = wakeWord();
    if (phrase) phraseTimer = setTimeout(() => savePhrase(phrase),
                                         PHRASE_SAVE_DEBOUNCE_MS);
  };
  loadPhrase();

  buildSourceOptions();

  $("playerrow").addEventListener("click", (e) => {
    if (!isPro() && PLAYERS.length > 1) { e.preventDefault(); showProUpsell(); }
  });
  $("player").onchange = () => {
    if (!isPro()) {         // locked, not disabled: put the choice back
      renderPlayers();
      showProUpsell();
      return;
    }
    localStorage.setItem("player", $("player").value);
    refreshNowPlaying();  // the mini-player follows the room immediately
  };
  loadPlayers();
}
