// Misheard names (Pro): the "remember" offer under an answer, and the
// settings section beside kid-safe (docs/name-recognition-design.md, phase 2).
//
// The server decides everything — whether to offer, what a correction does,
// whether the household is Pro — and answers every change with the whole new
// state, which is simply rendered. Nothing is kept unless somebody taps.

import { $ } from "./util.js";
import { ui } from "./i18n.js";

let NM = null;  // the last GET/POST /names answer

async function nmAction(body) {
  try {
    const r = await fetch("/names", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    NM = await r.json();
  } catch (e) { return null; }
  renderNames();
  return NM;
}

export async function refreshNames() {
  try {
    NM = await (await fetch("/names")).json();
  } catch (e) { NM = null; }
  renderNames();
}

// Under a typed answer that corrected a spoken one: «when you hear X, I mean
// Y?». One tap keeps it; the button then says so and stops being a button.
export function renderRemember(afterEl, offer) {
  if (!offer || !offer.heard || !offer.meant) return;
  const row = document.createElement("div");
  row.className = "choices";
  const btn = document.createElement("button");
  btn.className = "choice remember";
  btn.textContent = ui("nm_remember")(offer.heard, offer.meant);
  btn.onclick = async () => {
    btn.disabled = true;
    const d = await nmAction({ action: "remember", heard: offer.heard,
                               meant: offer.meant, lang: offer.lang });
    btn.textContent = d && d.ok ? ui("nm_remembered") : ui("nm_remember_failed");
  };
  row.appendChild(btn);
  afterEl.after(row);
}

export function renderNames() {
  const box = $("namesbox");
  if (!NM || !NM.available || !NM.pro) { box.style.display = "none"; return; }
  box.style.display = "";
  $("nmhistory").checked = !!NM.history_enabled;
  $("nmcount").textContent = ui("nm_count")(NM.history_count || 0);
  $("nmclear").disabled = !NM.history_count;
  const list = $("nmlist");
  list.innerHTML = "";
  const items = NM.corrections || [];
  if (!items.length) {
    const none = document.createElement("span");
    none.className = "hint";
    none.textContent = ui("nm_none");
    list.appendChild(none);
    return;
  }
  items.forEach(c => {
    const chip = document.createElement("button");
    chip.className = "choice";
    // textContent, never innerHTML: these are words somebody said.
    chip.textContent = "«" + c.heard + "» → «" + c.meant + "»  ✕";
    chip.title = ui("nm_forget");
    chip.onclick = () => nmAction({ action: "forget", id: c.id });
    list.appendChild(chip);
  });
}

export function initNames() {
  $("nmhistory").onchange = () =>
    nmAction({ action: "history", enabled: $("nmhistory").checked });
  $("nmclear").onclick = () => {
    if (window.confirm(ui("nm_clear_confirm"))) nmAction({ action: "clear_history" });
  };
}
