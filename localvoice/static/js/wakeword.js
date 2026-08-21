// Wake-word matching for the continuous (hands-free) listening mode: fuzzy
// token matching against what the recogniser heard, the "listening" beep, and
// the debounce that turns a growing utterance into exactly one command.

import { $ } from "./util.js";
import { ui } from "./i18n.js";
import { runCommand } from "./chat.js";
import { wakeWord } from "./settings.js";

const norm = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

// A short, self-contained "listening" cue for hands-free wake (no asset/CDN).
export function beep() {
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const o = ac.createOscillator(), g = ac.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ac.destination);
    g.gain.setValueAtTime(0.0001, ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.18, ac.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.18);
    o.start(); o.stop(ac.currentTime + 0.2);
  } catch (e) { /* audio optional */ }
}

// Fuzzy token match so common it-IT mis-hearings of the wake word still fire
// ("vivavoce" vs "viva voce"/"vivavoci"): equal, a ≥4-char prefix, or ≤1 edit.
function tokEq(a, b) {
  if (a === b) return true;
  if (a.length >= 4 && b.length >= 4 && (a.startsWith(b) || b.startsWith(a))) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0, j = 0, edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; }
    else { if (++edits > 1) return false;
      if (a.length > b.length) i++; else if (b.length > a.length) j++; else { i++; j++; } }
  }
  return edits + (a.length - i) + (b.length - j) <= 1;
}

// The command is the words AFTER the wake phrase; returns null if the wake
// phrase isn't present (accent/case-insensitive, fuzzy per token).
export function commandAfterWake(text) {
  const ww = norm(wakeWord()).split(/\s+/).filter(Boolean);
  if (!ww.length) return null;
  const words = (text || "").trim().split(/\s+/);
  const nw = words.map(norm);
  for (let i = 0; i + ww.length <= nw.length; i++) {
    let hit = true;
    for (let j = 0; j < ww.length; j++) if (!tokEq(nw[i + j], ww[j])) { hit = false; break; }
    if (hit) return words.slice(i + ww.length).join(" ");
  }
  return null;
}

// Wake mode is CONTINUOUS: the recogniser finalises a long phrase in pieces,
// so acting on each piece would fire half-typed commands ("metti Don't",
// "metti Don't stop", ...). Instead we accumulate the whole utterance and send
// the command once, ~1s after you stop talking (debounce), then reset the
// session so the next command starts clean.
export function createWakeHandler(rec) {
  let capTimer = null;

  function wakeResult(e) {
    // In this browser Chrome's continuous `results` are CUMULATIVE snapshots that
    // grow entry by entry — each one repeats the words before it ("vivavoce",
    // "vivavoce metti", "vivavoce metti Don't", ...), and even final entries do
    // this. Joining them duplicates every word ("vivavoce vivavoce metti ..."),
    // so take the single fullest (longest) transcript instead, which is the most
    // complete snapshot; use its alternatives when it's a final result.
    let best = null;
    for (let i = 0; i < e.results.length; i++) {
      const r = e.results[i];
      if (!best || r[0].transcript.length > best[0].transcript.length) best = r;
    }
    const txt = best ? (best[0].transcript || "").trim() : "";
    const alts = best && best.isFinal ? Array.from(best, (a) => a.transcript) : null;

    // Only act on speech that actually contains the wake word: ambient noise
    // (or a session restart every few seconds) must not trigger anything. No cue
    // on merely hearing the word — a single beep confirms only when a real
    // command is sent, so silence stays silent.
    const after = commandAfterWake(txt);        // null when the wake word isn't present
    if (after === null) {
      $("status").textContent = ui("listening_wake")(wakeWord());
      return;
    }
    const cmd = after.trim();
    if (!cmd) { $("status").textContent = ui("say_command"); return; }  // just the wake word

    $("status").textContent = "… " + cmd;
    clearTimeout(capTimer);                     // keep waiting while words keep coming
    capTimer = setTimeout(() => {
      beep();                                   // confirm only when the command is sent
      const strip = (s) => { const a = commandAfterWake(s); return a === null ? s : a; };
      const cleanAlts = (alts || []).map(strip).filter((x) => x && x.trim());
      runCommand(cmd, cleanAlts.length ? cleanAlts : [cmd]);
      try { rec.stop(); } catch (e) {}          // reset the session; onend restarts fresh
    }, 1000);
  }

  return { wakeResult, clearCap: () => clearTimeout(capTimer) };
}
