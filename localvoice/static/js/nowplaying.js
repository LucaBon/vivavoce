// Now-playing mini-player: polls /nowplaying, hides itself when nothing plays
// (or the LMS is unreachable — the endpoint answers mode "unknown", not 5xx),
// and drives the transport (pause/skip/seek/volume) through POST /player.

import { $ } from "./util.js";
import { ui, setLmsDown } from "./i18n.js";
import { currentPlayer } from "./settings.js";

const NP_POLL_MS = 5000;
let npLastArt = null;
// Last poll snapshot + when it arrived: the 1 s ticker extrapolates elapsed
// between polls so the time/bar move smoothly instead of jumping every 5 s.
let npState = null;
let npSeeking = false;  // finger on the bar: nothing may overwrite the UI
let npVolDrag = false;  // finger on the volume slider: polls keep hands off

function fmtTime(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m))
       + ":" + String(sec).padStart(2, "0");
}
function npNow() {
  if (!npState || npState.elapsed == null) return 0;
  let e = npState.elapsed;
  if (npState.mode === "play") e += (performance.now() - npState.syncedAt) / 1000;
  return npState.duration ? Math.min(e, npState.duration) : e;
}
function renderNpTime() {
  if (!npState || npSeeking) return;
  const dur = npState.duration || 0, cur = npNow();
  $("npel").textContent = fmtTime(cur);
  $("npdur").textContent = dur ? fmtTime(dur) : "–:––";
  $("npfill").style.width = (dur ? Math.min(100, 100 * cur / dur) : 0) + "%";
  const seek = $("npseek");
  seek.classList.toggle("nodur", !dur);
  seek.setAttribute("aria-disabled", dur ? "false" : "true");
  seek.setAttribute("aria-valuemax", String(Math.round(dur)));
  seek.setAttribute("aria-valuenow", String(Math.round(cur)));
  seek.setAttribute("aria-valuetext",
    fmtTime(cur) + (dur ? " / " + fmtTime(dur) : ""));
}
export function renderNowPlaying(d) {
  const el = $("np");
  if (!d || !d.title || (d.mode !== "play" && d.mode !== "pause")) {
    el.hidden = true;
    npLastArt = null;
    npState = null;
    return;
  }
  el.hidden = false;
  el.classList.toggle("paused", d.mode === "pause");
  el.setAttribute("aria-label", ui("np_label"));
  $("npprev").setAttribute("aria-label", ui("np_prev"));
  $("nptoggle").setAttribute("aria-label", ui("np_toggle"));
  $("npnext").setAttribute("aria-label", ui("np_next"));
  $("npseek").setAttribute("aria-label", ui("np_seek"));
  $("npvol").setAttribute("aria-label", ui("np_vol"));
  const volrow = $("npvolrow");
  if (d.volume == null) {
    volrow.hidden = true;
  } else {
    volrow.hidden = false;
    if (!npVolDrag) setVolUI(d.volume);
  }
  $("nptitle").textContent = d.title;
  $("npsub").textContent = [d.artist, d.album].filter(Boolean).join(" · ");
  const img = $("npart");
  if (d.artwork && d.artwork !== npLastArt) {
    npLastArt = d.artwork;
    img.hidden = false;
    img.onerror = () => { img.hidden = true; };
    img.src = d.artwork;
  } else if (!d.artwork) {
    img.hidden = true;
    npLastArt = null;
  }
  npState = { mode: d.mode, elapsed: d.elapsed, duration: d.duration || 0,
              syncedAt: performance.now() };
  renderNpTime();
}
// The poll runs on a timer AND after every command, so two can overlap — and
// with no ordering the slower, older answer landed last and painted a stale
// track over the fresh one. A sequence number keeps the newest reply the one
// that wins; a deadline keeps a hung request from blocking the next poll for
// as long as the browser feels like waiting.
const NOWPLAYING_TIMEOUT_MS = 8000;
let npSeq = 0;
let npRendered = 0;

export async function refreshNowPlaying() {
  const seq = ++npSeq;
  const stale = () => seq < npRendered;
  try {
    const p = currentPlayer();
    const r = await fetch("/nowplaying"
                          + (p ? "?player=" + encodeURIComponent(p) : ""),
                          { signal: AbortSignal.timeout
                              ? AbortSignal.timeout(NOWPLAYING_TIMEOUT_MS)
                              : undefined });
    const d = await r.json();
    if (stale()) return;
    npRendered = seq;
    setLmsDown(d.mode === "unknown");
    renderNowPlaying(d);
  } catch (e) {
    if (stale()) return;
    npRendered = seq;
    // Offline is not "the LMS is down": the phone left the Wi-Fi, or the
    // screen slept. Saying the hi-fi is unreachable sends people to look at
    // the wrong box entirely.
    setLmsDown(true, navigator.onLine === false);
    renderNowPlaying(null);
  }
}

// --- Mini-player transport: POST /player, render the returned status so the
// card syncs immediately instead of waiting for the next poll.
async function playerAction(action, seconds, value) {
  const body = { action, player: currentPlayer() };
  if (seconds != null) body.seconds = seconds;
  if (value != null) body.value = value;
  try {
    const r = await fetch("/player", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const d = await r.json();
    if (d && d.ok) renderNowPlaying(d);
  } catch (e) { /* the next poll re-syncs */ }
}

function setVolUI(value) {
  const npvolEl = $("npvol");
  npvolEl.value = value;
  npvolEl.style.setProperty("--vol", value + "%");
}

export function initNowPlaying() {
  setInterval(() => { if (!document.hidden) refreshNowPlaying(); }, NP_POLL_MS);
  setInterval(() => {
    if (!document.hidden && npState && npState.mode === "play") renderNpTime();
  }, 1000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshNowPlaying();
  });
  refreshNowPlaying();

  $("npprev").onclick = () => playerAction("prev");
  $("npnext").onclick = () => playerAction("next");
  $("nptoggle").onclick = () => {
    if (!npState) return;
    const cur = npNow(), pausing = npState.mode === "play";
    // Optimistic: freeze/restart the ticker and swap the icon right away.
    npState.mode = pausing ? "pause" : "play";
    npState.elapsed = cur;
    npState.syncedAt = performance.now();
    $("np").classList.toggle("paused", pausing);
    playerAction(pausing ? "pause" : "resume");
  };

  // --- Seek bar: drag or tap anywhere on the strip; keyboard ±10 s. While the
  // pointer is down only the preview updates (npSeeking blocks poll/ticker),
  // the LMS "time" command fires once on release.
  const seekEl = $("npseek");
  function seekTime(ev) {
    const r = seekEl.getBoundingClientRect();
    const pct = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
    return pct * npState.duration;
  }
  function seekPreview(t) {
    $("npfill").style.width = (100 * t / npState.duration) + "%";
    $("npel").textContent = fmtTime(t);
  }
  seekEl.addEventListener("pointerdown", (ev) => {
    if (!npState || !npState.duration) return;
    npSeeking = true;
    seekEl.classList.add("drag");
    seekEl.setPointerCapture(ev.pointerId);
    seekPreview(seekTime(ev));
    ev.preventDefault();
  });
  seekEl.addEventListener("pointermove", (ev) => {
    if (npSeeking) seekPreview(seekTime(ev));
  });
  seekEl.addEventListener("pointerup", (ev) => {
    if (!npSeeking) return;
    npSeeking = false;
    seekEl.classList.remove("drag");
    const t = seekTime(ev);
    npState.elapsed = t;
    npState.syncedAt = performance.now();
    renderNpTime();
    playerAction("seek", Math.round(t));
  });
  seekEl.addEventListener("pointercancel", () => {
    npSeeking = false;
    seekEl.classList.remove("drag");
    renderNpTime();
  });
  seekEl.addEventListener("keydown", (ev) => {
    if (!npState || !npState.duration) return;
    const step = ev.key === "ArrowRight" ? 10 : ev.key === "ArrowLeft" ? -10 : 0;
    if (!step) return;
    ev.preventDefault();
    const t = Math.min(npState.duration, Math.max(0, npNow() + step));
    npState.elapsed = t;
    npState.syncedAt = performance.now();
    renderNpTime();
    playerAction("seek", Math.round(t));
  });

  // --- Volume slider: the drag previews locally (npVolDrag keeps the poll's
  // hands off); the LMS command fires once on release, not per pixel. --vol
  // paints the amber filled side of the track (CSS can't, on a range input).
  const npvolEl = $("npvol");
  npvolEl.addEventListener("input", () => {
    npVolDrag = true;
    npvolEl.style.setProperty("--vol", npvolEl.value + "%");
  });
  npvolEl.addEventListener("change", () => {
    npVolDrag = false;
    playerAction("volume", null, Number(npvolEl.value));
  });
  npvolEl.addEventListener("pointercancel", () => { npVolDrag = false; });
}
