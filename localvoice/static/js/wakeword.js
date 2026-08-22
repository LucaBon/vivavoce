// Wake-word matching for the continuous (hands-free) listening mode: fuzzy
// token matching against what the recogniser heard, the "listening" beep, and
// the debounce that turns a growing utterance into exactly one command.

import { $ } from "./util.js";
import { ui } from "./i18n.js";
import { runCommand } from "./chat.js";
import { wakeWord } from "./settings.js";

const norm = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

// A short, self-contained "listening" cue for hands-free wake (no asset/CDN).
//
// The context is closed when the tone ends. Chrome caps a page at ~6 live
// AudioContexts and then makes `new AudioContext()` THROW: leaking one per
// beep meant that after a handful of wake triggers the next context creation
// failed — and with server-side wake word that context is the microphone
// stream itself (serverwake.js), so the failure surfaced as the mic simply
// switching itself off mid-session.
export function beep() {
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const o = ac.createOscillator(), g = ac.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(ac.destination);
    g.gain.setValueAtTime(0.0001, ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.18, ac.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.18);
    o.start(); o.stop(ac.currentTime + 0.2);
    o.onended = () => { try { ac.close(); } catch (e) {} };
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

// How long "yes? tell me the command" stays true after hearing the wake word
// on its own. Long enough to draw breath and speak, short enough that a room
// left alone goes back to ignoring everything it hears.
const ARMED_MS = 10000;

// Wake mode is CONTINUOUS: the recogniser finalises a long phrase in pieces,
// so acting on each piece would fire half-typed commands ("metti Don't",
// "metti Don't stop", ...). Instead we accumulate the whole utterance and send
// the command once, ~1s after you stop talking (debounce), then reset the
// session so the next command starts clean.
//
// Two ways to speak, both supported. One breath — "vivavoce metti i Pink
// Floyd" — or two steps: say the wake word, get asked for the command, say it.
// The second used to be advertised and then not work: saying the wake word
// alone printed "yes? tell me the command", and Chrome ends a continuous
// session every few seconds, so the command arrived in a NEW session whose
// transcript no longer contained the wake word — commandAfterWake() returned
// null and it was discarded in silence, the prompt quietly replaced by
// "listening…" again. Hence `armed`: once the wake word has been heard on its
// own, the next thing said IS the command, session restarts included.
export function createWakeHandler(rec) {
  let capTimer = null;
  let armed = false, armedTimer = null;

  function disarm() { armed = false; clearTimeout(armedTimer); }
  function arm() {
    armed = true;
    clearTimeout(armedTimer);
    armedTimer = setTimeout(() => {
      armed = false;
      $("status").textContent = ui("listening_wake")(wakeWord());
    }, ARMED_MS);
  }

  // Debounced send, shared by both ways of speaking: keep waiting while words
  // keep coming, then fire once and reset the session.
  function sendWhenDone(cmd, alts) {
    clearTimeout(capTimer);
    capTimer = setTimeout(() => {
      disarm();
      beep();                                   // confirm only when the command is sent
      // Strip the wake word from each alternative when it carries one; in the
      // two-step flow it doesn't, and the alternative passes through as-is.
      const strip = (s) => { const a = commandAfterWake(s); return a === null ? s : a; };
      const cleanAlts = (alts || []).map(strip).filter((x) => x && x.trim());
      runCommand(cmd, cleanAlts.length ? cleanAlts : [cmd]);
      try { rec.stop(); } catch (e) {}          // reset the session; onend restarts fresh
    }, 1000);
  }

  function wakeResult(e) {
    // In this browser Chrome's continuous `results` are CUMULATIVE snapshots that
    // grow entry by entry — each one repeats the words before it ("vivavoce",
    // "vivavoce metti", "vivavoce metti Don't", ...), and even final entries do
    // this. Joining them duplicates every word ("vivavoce vivavoce metti ..."),
    // so act on ONE entry: the last, which for a growing utterance is the
    // fullest snapshot of it.
    //
    // Not the LONGEST, which is what this used to take. Snapshots grow within
    // one utterance, but a second utterance in the same session starts a fresh
    // entry — so the two-step flow left ["vivavoce", "pausa"] here, and the
    // longest of those is the wake word. Every command spoken promptly after
    // the prompt was thrown away in favour of the phrase that asked for it,
    // and the panel just asked again.
    const entries = Array.from(e.results, (r) => r);
    const textOf = (r) => ((r && r[0] && r[0].transcript) || "").trim();
    let best = entries[entries.length - 1] || null;
    // One guard kept from the longest-wins rule it replaces: a stray short
    // interim can arrive after a fuller snapshot. When the last entry carries
    // no wake word and none was expected, fall back to the fullest that does.
    if (best && !armed && commandAfterWake(textOf(best)) === null) {
      for (const r of entries) {
        if (commandAfterWake(textOf(r)) !== null
            && textOf(r).length > textOf(best).length) best = r;
      }
    }
    const txt = textOf(best);
    const alts = best && best.isFinal ? Array.from(best, (a) => a.transcript) : null;

    // Only act on speech that actually contains the wake word: ambient noise
    // (or a session restart every few seconds) must not trigger anything. No cue
    // on merely hearing the word — a single beep confirms only when a real
    // command is sent, so silence stays silent.
    const after = commandAfterWake(txt);        // null when the wake word isn't present
    if (after === null) {
      // No wake word here. Normally that's ambient noise to ignore — unless
      // we just asked for a command, in which case this is it.
      const heard = txt.trim();
      if (armed && heard) {
        $("status").textContent = "… " + heard;
        sendWhenDone(heard, alts);
      } else if (!armed) {
        $("status").textContent = ui("listening_wake")(wakeWord());
      }
      return;
    }
    const cmd = after.trim();
    if (!cmd) {                                 // just the wake word: ask, and wait
      arm();
      $("status").textContent = ui("say_command");
      return;
    }

    disarm();                                   // wake word and command in one breath
    $("status").textContent = "… " + cmd;
    sendWhenDone(cmd, alts);
  }

  return {
    wakeResult,
    // mic.js consults this so a session restart mid-question doesn't wipe the
    // "tell me the command" prompt, nor blink the button as if listening had
    // stopped while it is in fact still waiting for an answer.
    isArmed: () => armed,
    clearCap: () => { clearTimeout(capTimer); disarm(); },
  };
}
