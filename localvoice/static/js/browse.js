// Material Skin, opened inside the page instead of in another tab.
//
// The link at the bottom of the page has always worked and still does: when
// the server sends no browse path — Material living somewhere other than the
// LMS we talk to — this module wires nothing and the click leaves the app the
// way it did before. With a path, the click opens a panel over the scrolling
// area and the microphone stays where it is, one tap away.
//
// The iframe is loaded lazily, at the first open: Material is a whole
// application, and every visit to the page should not pay for it. Closing
// keeps the src, so re-opening lands back where the user was.

import { $ } from "./util.js";

let path = "";       // where to point the frame; "" = no panel, plain link
let loaded = false;  // the frame has been given its src

function open() {
  const frame = $("browseframe");
  if (!loaded) { frame.src = path; loaded = true; }
  $("browse").hidden = false;
  document.body.classList.add("browsing");
}

function close() {
  $("browse").hidden = true;
  document.body.classList.remove("browsing");
}

export function initBrowse() {
  path = (window.VIVAVOCE_CFG || {}).browse || "";
  if (!path) return;
  $("material").addEventListener("click", (e) => {
    e.preventDefault();
    open();
    // A history entry, so the phone's Back button closes the panel rather
    // than leaving the app — which is what "back" means from in here.
    history.pushState({ browse: true }, "");
  });
  $("browseclose").onclick = () => {
    if (history.state && history.state.browse) history.back();
    else close();
  };
  window.addEventListener("popstate", close);
}

// Kid-safe: a locked device does not get the door to a UI that can start
// anything at all by touch. Called from renderKidsafe(), which applyUI() also
// calls, so this survives a language change without a hook of its own.
//
// A defence of the interface, not of the server: whoever knows the URL still
// reaches it. The external link had the same hole and had it in plain sight,
// so this is strictly less open than before, and the honest place for the
// real gate is the router, where the voice commands are already refused.
export function applyBrowse(kidsafe) {
  const blocked = !!(kidsafe && kidsafe.enabled && kidsafe.locked);
  $("material").style.display = blocked ? "none" : "";
  if (blocked) close();
}
