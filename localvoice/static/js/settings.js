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
// /command, /player, /nowplaying — only when Pro, so a stale value is inert.
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
  sel.disabled = !isPro();
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

export function initSettings() {
  $("wakeword").value = localStorage.getItem("wakeword") || "vivavoce";
  $("wwlabel").textContent = wakeWord();
  $("wakeword").oninput = () => {
    localStorage.setItem("wakeword", $("wakeword").value);
    $("wwlabel").textContent = wakeWord();
  };

  buildSourceOptions();

  $("playerrow").addEventListener("click", (e) => {
    if (!isPro() && PLAYERS.length > 1) { e.preventDefault(); showProUpsell(); }
  });
  $("player").onchange = () => {
    localStorage.setItem("player", $("player").value);
    refreshNowPlaying();  // the mini-player follows the room immediately
  };
  loadPlayers();
}
