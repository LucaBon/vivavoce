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

// Both hints quote the same field, because there is one server engine now and
// it hears the phrase the household typed. The override this used to carry —
// a fixed English model phrase the field could not change, which therefore
// had to grey the field out and replace the hint — went with openWakeWord.
export function syncWakeLabel() {
  const phrase = wakeWord();
  for (const id of ["wwlabel", "wwlabel_srv"]) {
    const el = $(id);
    if (el) el.textContent = phrase;
  }
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
    if (d.ok) {
      // `unverified` means the lexicon check could not vouch for itself, so
      // the phrase was saved without being checked. Saying so is the point:
      // a check that has silently stopped working accepts invented phrases
      // that then never fire, which is the failure the check exists for.
      showPhraseMessage(d.unverified ? ui("wake_phrase_unverified")
                                     : ui("wake_phrase_saved"),
                        !!d.unverified);
      return;
    }
    if (d.error === "out_of_vocabulary" && (d.words || []).length) {
      // Kept locally on purpose: the BROWSER engine has no lexicon and hears
      // this perfectly well. What is refused is the household-wide setting,
      // and saying which word is the whole value of the refusal.
      showPhraseMessage(ui("wake_phrase_rejected")(d.words), true);
      return;
    }
    // "unavailable" is the ordinary answer on a box without the engine, and
    // there is nothing for the user to do about it: stay quiet. Anything
    // else is a refused write — the server goes out of its way NOT to report
    // success over one (appdata.set_wake_phrase raises rather than swallow
    // it), and clearing the box here threw that care away at the last step:
    // a read-only data directory looked exactly like a save.
    if (d.error && d.error !== "unavailable") {
      showPhraseMessage(ui("wake_phrase_failed")(d.error), true);
      return;
    }
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
    // `stored` is the whole reason this is not a plain assignment. An
    // unconfigured house answers "vivavoce" because that is the DEFAULT, not
    // because anybody chose it — and before this endpoint existed the phrase
    // lived only in each browser's localStorage. Overwriting on that answer
    // silently deleted the only copy of a phrase a household had been using
    // for months, on the first page load after the update.
    if (d.stored) {
      $("wakeword").value = d.phrase;
      localStorage.setItem("wakeword", d.phrase);
      syncWakeLabel();
      return;
    }
    // Nobody has chosen yet: this browser's value is the only answer there
    // is, so it migrates UP instead of being replaced. Once it lands, the
    // server has it and the rest of the house inherits it.
    const local = wakeWord();
    if (local && local !== d.phrase) savePhrase(local);
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
