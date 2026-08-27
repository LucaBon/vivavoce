// Pro license state and the kid-safe panel (both server-enforced).
//
// The truth lives server-side (/license, cached activation file); the page
// keeps a localStorage hint so an offline Pro household still gets its mic
// button (server-enforced features re-check server-side anyway). Never baked
// into the served HTML: the PWA-cached copy must not carry stale state.

import { $, clientId } from "./util.js";
import { ui } from "./i18n.js";
import { syncVoicePanel } from "./tts.js";
import { syncWakePhrase } from "./miccapture.js";
import { renderPlayers } from "./settings.js";

const PRO_STORE_URL = "https://vivavoce.lemonsqueezy.com";  // checkout link, set at launch
let PRO = localStorage.getItem("pro_hint") === "1";
let PRO_INFO = null;

export const isPro = () => PRO;

// The trial block from /license ({active, expired, day, days_left, days}), or
// null when the page has never reached the server. `day` keeps counting after
// the window closes — chat.js times the in-flow prompt off it.
export const trialInfo = () => (PRO_INFO && PRO_INFO.trial) || null;
// Somebody actually paid. Distinct from isPro(), which an open window also
// satisfies: the difference decides whether the panel offers to sell anything.
export const isLicensed = () => !!(PRO_INFO && PRO_INFO.key);

export function applyPro() {
  $("mic").classList.toggle("locked", !PRO);
  $("wakemode").disabled = !PRO;
  $("readback").disabled = !PRO;
  $("localasr").disabled = !PRO;
  $("serverwake").disabled = !PRO;
  if (!PRO) {
    if ($("wakemode").checked) {
      $("wakemode").checked = false;
      // #wakeopts, not #wakehint: the index.html split moved the container
      // out from under that id (which is now just the inner hint text), and
      // this kept hiding the paragraph while the block around it — engine
      // choice, wake-word field, the lot — stayed on screen under a disabled
      // checkbox. It is what mic.js toggles, so it is what belongs here.
      $("wakeopts").style.display = "none";
    }
    if ($("readback").checked) { $("readback").checked = false; syncVoicePanel(); }
    $("localasr").checked = false;
    $("serverwake").checked = false;
    // The engine choice has a reconciler and this is a change to it: without
    // asking it to run, the panel keeps the server engine's hint and its
    // disabled wake-word field while the browser engine is what would
    // actually run.
    syncWakePhrase();
  }
  const st = $("prostatus");
  st.classList.remove("warn");
  const trial = trialInfo();
  // Pro because the first-install window is open, with nobody having paid.
  // Saying "Pro active — license ****" here would be a lie the user finds out
  // about on day 15, which is the worst possible day to find it out.
  const onTrial = !!(trial && trial.active && !isLicensed());
  // A page that never reached the server (offline, PWA cold open) keeps its
  // localStorage hint and is treated as paid: it is what it was last told,
  // and a paying household must not be shown a buy button on a flaky boot.
  const showBuy = onTrial || !PRO;
  $("prorow").style.display = showBuy ? "" : "none";
  $("probuy").style.display = showBuy ? "inline-block" : "none";
  $("probuy").href = PRO_STORE_URL;
  if (onTrial) {
    // Emphasised only at the end, when the number has become news.
    if (trial.days_left <= 3) st.classList.add("warn");
    st.innerHTML = ui("pro_trial")(trial.days_left);
  } else if (PRO) {
    st.textContent = ui("pro_active")((PRO_INFO && PRO_INFO.key) || "****");
  } else if (PRO_INFO && PRO_INFO.revoked) {
    st.classList.add("warn");
    st.innerHTML = ui("pro_revoked");
  } else if (trial && trial.expired) {
    st.innerHTML = ui("pro_trial_over");
  } else {
    st.innerHTML = ui("pro_pitch");
  }
  renderPlayers();  // the room selector locks/unlocks with the license
}

function setPro(info) {
  PRO = !!(info && info.pro);
  PRO_INFO = info || null;
  localStorage.setItem("pro_hint", PRO ? "1" : "0");
  applyPro();
}

export async function refreshLicense() {
  try {
    const r = await fetch("/license");
    setPro(await r.json());
  } catch (e) { applyPro(); }  // offline/static: keep the last hint
}

export function showProUpsell() {
  $("settings").open = true;
  $("probox").scrollIntoView({ behavior: "smooth", block: "center" });
}

// --- Kid-safe panel (Pro, server-enforced): state comes from /kidsafe. ---
let KS = null;

export function renderKidsafe() {
  const box = $("kidsafebox");
  if (!KS) { box.style.display = "none"; $("kschip").style.display = "none"; return; }
  box.style.display = "";
  $("kschip").style.display = KS.enabled ? "" : "none";
  const st = $("ksstatus");
  const unlocked = KS.enabled && !KS.locked;
  // status line + which controls show
  if (!KS.enabled) {
    st.innerHTML = ui("ks_pitch") + (KS.pro ? "" :
      ' <span class="warn">' + ui("pro_only").replace(/^ — /, "") + "</span>");
    $("kspin").placeholder = KS.haspin ? ui("ks_pin_ph") : ui("ks_pin_new_ph");
    $("ksgo").textContent = ui("ks_enable_btn");
    $("ksrow").style.display = "";
  } else if (KS.locked) {
    st.innerHTML = '<span class="lamp"></span>' + ui("ks_locked_line") +
      (KS.pro ? "" : ' <span class="warn">' + ui("ks_revoked_note") + "</span>");
    $("kspin").placeholder = ui("ks_pin_ph");
    $("ksgo").textContent = ui("ks_unlock_btn");
    $("ksrow").style.display = "";
  } else {
    st.innerHTML = '<span class="lamp"></span>' + ui("ks_open_line");
    $("ksrow").style.display = "none";
  }
  $("ksaddrow").style.display = unlocked ? "" : "none";
  $("ksbuttons").style.display = unlocked ? "" : "none";
  const terms = $("ksterms");
  terms.innerHTML = "";
  terms.style.display = unlocked ? "" : "none";
  if (unlocked) {
    if (!(KS.terms || []).length) {
      terms.innerHTML = '<span class="hint">' + ui("ks_empty") + "</span>";
    } else {
      KS.terms.forEach(term => {
        const chip = document.createElement("button");
        chip.className = "choice";
        chip.textContent = term + "  ✕";
        chip.onclick = () => ksAction("remove", { term });
        terms.appendChild(chip);
      });
    }
  }
}

async function ksAction(action, extra) {
  try {
    const r = await fetch("/kidsafe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ client: clientId(), action }, extra || {}))
    });
    const d = await r.json();
    KS = d;
    renderKidsafe();
    if (!d.ok) {
      const st = $("ksstatus");
      if (d.error === "pro_required") { showProUpsell(); }
      else if (d.error === "wrong_pin") {
        st.innerHTML += ' <span class="warn">' + ui("ks_wrong_pin") + "</span>";
      } else if (d.error === "locked_out") {
        st.innerHTML += ' <span class="warn">'
          + ui("ks_locked_out")(d.retry_in || 0) + "</span>";
      } else if (d.error === "pin_too_short") {
        st.innerHTML += ' <span class="warn">' + ui("ks_pin_short") + "</span>";
      } else if (d.error === "save_failed" && d.speech) {
        // The server already phrased this one, in the user's language, and it
        // carries the term they typed — so it goes in as text, never markup.
        const warn = document.createElement("span");
        warn.className = "warn";
        warn.textContent = " " + d.speech;
        st.appendChild(warn);
      }
    }
    return d;
  } catch (e) { return null; }
}

export async function refreshKidsafe() {
  try {
    const r = await fetch("/kidsafe?client=" + encodeURIComponent(clientId()));
    KS = await r.json();
  } catch (e) { KS = null; }
  renderKidsafe();
}

export function initPro() {
  $("proact").onclick = async () => {
    const key = $("prokey").value.trim();
    if (!key) return;
    $("proact").disabled = true;
    const st = $("prostatus");
    try {
      const r = await fetch("/license", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key })
      });
      const d = await r.json();
      if (d.ok) { $("prokey").value = ""; setPro(d); }
      else {
        st.classList.add("warn");
        st.textContent = d.error === "network"
          ? ui("pro_err_network") : ui("pro_err_invalid") + (d.detail || "");
      }
    } catch (e) {
      st.classList.add("warn");
      st.textContent = ui("pro_err_network");
    } finally {
      $("proact").disabled = false;
    }
  };

  $("ksgo").onclick = async () => {
    const pin = $("kspin").value;
    if (!KS) return;
    if (!KS.enabled && !PRO) { showProUpsell(); return; }
    const d = await ksAction(KS.enabled ? "unlock" : "enable", { pin });
    if (d && d.ok) $("kspin").value = "";
  };
  $("kspin").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("ksgo").click();
  });
  $("ksadd").onclick = async () => {
    const term = $("ksterm").value.trim();
    if (!term) return;
    const d = await ksAction("add", { term });
    if (d && d.ok) $("ksterm").value = "";
  };
  $("ksterm").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("ksadd").click();
  });
  $("kslock").onclick = () => ksAction("lock");
  $("ksdisable").onclick = () => ksAction("disable");
}
