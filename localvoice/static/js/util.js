// Tiny shared helpers: DOM lookup and the per-browser client id.

export const $ = (id) => document.getElementById(id);

// Stable per-browser id so this device's "metti la N" list stays its own on the
// server (two phones don't clobber each other).
export function clientId() {
  let id = localStorage.getItem("vivavoce_client")
        || localStorage.getItem("impianto_client");  // pre-rename installs
  if (!id) {
    id = Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
  localStorage.setItem("vivavoce_client", id);
  return id;
}
