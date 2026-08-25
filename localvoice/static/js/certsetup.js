// The certificate onboarding: recognise "not trusted", explain the fix for
// THIS device, and check by itself that it worked.
//
// Why this is worth a module. The microphone needs a secure context, so the
// browser's "your connection is not private" warning stands exactly in front
// of the feature people pay for. Everything needed to remove it already
// existed — tools/make_cert.py makes a local CA, the server offers it at
// /ca.pem — and none of it helped, because the instructions sat collapsed at
// the bottom of the page, showed all four platforms at once, and left the
// user with no way to tell whether any of it had worked.
//
// The check is not a guess. Chrome (and Safari, and Firefox) refuse to
// register a service worker on an untrusted certificate, even after the user
// clicks through the warning — so `register()` resolving IS the proof that
// the CA is installed, and its rejection is the proof that it is not. That is
// also why registration lives here rather than in app.js: the same call
// answers "is the PWA installable?" and "is this certificate trusted?",
// which turn out to be the same question.

import { $ } from "./util.js";
import { ui } from "./i18n.js";

// Set once the answer is known: "ok" | "untrusted" | "nocert" | "http" |
// "local" | "unknown" (a browser with no service workers, where nothing here
// can be verified and saying so is the only honest option).
let state = "unknown";
let hasCA = false;
// Survives the reload the verify button triggers, so the panel can open on
// the answer instead of making the user find it again.
const VERIFY_FLAG = "cert_verify";

export function platform() {
  const ua = navigator.userAgent || "";
  // iPadOS 13+ reports itself as a Mac; the touch points give it away.
  if (/iPhone|iPad|iPod/.test(ua)
      || (/Mac/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Windows/.test(ua)) return "windows";
  if (/Mac/.test(ua)) return "macos";
  return "other";
}

const isLocalhost = () =>
  location.hostname === "localhost" || location.hostname === "127.0.0.1";

/** Register the service worker, reporting whether the certificate is trusted.
 *
 * A rejection here is the normal, expected state on a fresh install — not an
 * error to report. It is the signal the whole panel is built on.
 */
async function serviceWorkerTrusts() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    await navigator.serviceWorker.register("/sw.js");
    return true;
  } catch (e) {
    return false;
  }
}

async function resolveState() {
  if (location.protocol !== "https:") {
    // Plain HTTP: on this machine everything works (localhost is a secure
    // context by definition); from a phone it cannot, and no certificate
    // installed on the phone would change that — the server has to serve
    // TLS first. Nothing to guide here, so the panel says which it is.
    return isLocalhost() ? "local" : "http";
  }
  const trusted = await serviceWorkerTrusts();
  if (trusted === null) return "unknown";
  if (trusted) return "ok";
  return hasCA ? "untrusted" : "nocert";
}

function stepsFor(p) {
  const steps = ui("cert_steps")(p);
  return steps.map(html => "<li>" + html + "</li>").join("");
}

export function renderCertSetup() {
  const panel = $("installpanel");
  if (!panel) return;
  const stateEl = $("certstate");
  stateEl.className = "certstate " + state;
  stateEl.innerHTML = ui("cert_state_" + state);
  // Steps only where there is something to install: with no CA on the server,
  // or on a device that already trusts it, a list of steps is noise.
  const guiding = state === "untrusted" || state === "unknown";
  $("certsteps").innerHTML = guiding ? stepsFor(platform()) : "";
  $("certactions").style.display = guiding ? "" : "none";
  $("certverify").textContent = ui("cert_verify_btn");
  $("certother").textContent = $("certallsteps").hidden
    ? ui("cert_other_btn") : ui("cert_other_hide");
}

export async function initCertSetup() {
  try {
    hasCA = !!(await (await fetch("/tls")).json()).ca;
  } catch (e) {
    // A failed /tls means we do not KNOW whether the server has a CA — a
    // dropped Wi-Fi answers the same way a server without one does. It was
    // being read as "no CA on the server", which walks the user through
    // fixing something that isn't broken. Assume there is one: the worst
    // case is offering an install that then can't be downloaded, and the
    // steps say to fetch /ca.pem, which will fail visibly.
    hasCA = true;
  }
  state = await resolveState();

  $("certverify").onclick = () => {
    // The certificate for the page currently open was already accepted (or
    // refused) when this connection was made: installing the CA changes
    // nothing until the page is loaded again. So the button reloads, and the
    // flag below makes the answer the first thing seen afterwards.
    try { sessionStorage.setItem(VERIFY_FLAG, "1"); } catch (e) {}
    location.reload();
  };
  $("certother").onclick = () => {
    $("certallsteps").hidden = !$("certallsteps").hidden;
    renderCertSetup();
  };

  renderCertSetup();

  // Open the panel on its own only when it has something to say: right after
  // a verify attempt, or when the mic is behind an untrusted certificate.
  let verifying = false;
  try {
    verifying = sessionStorage.getItem(VERIFY_FLAG) === "1";
    sessionStorage.removeItem(VERIFY_FLAG);
  } catch (e) {}
  if (verifying || state === "untrusted") $("installpanel").open = true;
}

/** For the tests and the status line: what the certificate check concluded. */
export const certState = () => state;
