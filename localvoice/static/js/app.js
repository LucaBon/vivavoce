// Entry point: wires the modules together in the same order the old single
// <script> ran, then boots the page. Keep the order — the IT markup snapshot
// must precede any rewrite, and the mic setup decides the status line that
// applyUI() then renders.

import { $ } from "./util.js";
import { initI18n, setUIHooks, applyUI, setLmsDown } from "./i18n.js";
import { initTts, buildVoicePickers } from "./tts.js";
import { initChat, bubble, send } from "./chat.js";
import { initPro, applyPro, renderKidsafe, refreshLicense, refreshKidsafe,
         showProUpsell } from "./pro.js";
import { initSettings, buildSourceOptions, renderPlayers, setPlayersData } from "./settings.js";
import { initNowPlaying, renderNowPlaying } from "./nowplaying.js";
import { initMic, refreshAsr, refreshServerWake } from "./mic.js";

initI18n();  // snapshot the Italian markup before anything rewrites it
setUIHooks({ buildSourceOptions, buildVoicePickers, applyPro, renderKidsafe });
initChat();
initTts();
initPro();
initSettings();
initNowPlaying();
initMic();

// Render the UI in the selected language (labels, source options, status line).
applyUI();
// Ask the server for the real license state (the localStorage hint bridges
// the gap and offline opens).
refreshLicense();
refreshKidsafe();
refreshAsr();
refreshServerWake();

// First-ever visit: open the settings panel so language and source get noticed.
if (!localStorage.getItem("reclang") && !localStorage.getItem("source")) {
  $("settings").open = true;
}

// PWA: registra il service worker (shell offline + installabilità). Chrome lo
// accetta solo su HTTPS *fidato* — cioè con la CA locale installata (vedi il
// pannello «Installa come app»), non col certificato accettato dopo l'avviso.
// Il fallimento è normale e silenzioso finché la CA non è installata.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// Test/tooling hook: the screenshot harness (tools/ui_shots.py) and the e2e
// suite drive page internals that ES modules no longer leak as globals.
// Not a public API.
window.vivavoce = { bubble, send, renderNowPlaying, renderPlayers,
                    setPlayersData, setLmsDown, applyUI, showProUpsell,
                    refreshLicense, refreshKidsafe, refreshAsr, refreshServerWake };
