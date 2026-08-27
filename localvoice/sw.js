// Service worker minimale per la PWA Vivavoce.
//
// Strategia: network-first per la pagina *e per /static/* (un aggiornamento
// del server arriva subito; la cache serve solo da fallback offline), e
// cache-first per i soli asset davvero immutabili (icone, manifest).
// I comandi (/api/v1/command e il suo alias /command) non passano mai dalla
// cache: sono POST, e il filtro sul metodo qui sotto li lascia sempre alla rete.
//
// Perché /static/ è network-first e non cache-first: staticfiles.py rilegge
// quei file a ogni richiesta apposta, "così una modifica arriva con un
// refresh". Con cache-first il service worker annullava quella scelta —
// un mic.js corretto restava invisibile all'app installata finché non si
// bumpava VERSION a mano, e la modifica sembrava semplicemente non funzionare.
//
// Nota: Chrome registra il service worker solo su HTTPS *fidato* — quindi con
// la CA locale installata (vedi /ca.pem), non con il certificato "accettato
// nonostante l'avviso".
const VERSION = "vivavoce-v11";
const SHELL = ["/", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png",
               "/static/css/app.css",
               "/static/js/app.js", "/static/js/certsetup.js",
               "/static/js/chat.js", "/static/js/i18n.js",
               "/static/js/localasr.js",
               "/static/js/mic.js", "/static/js/miccapture.js",
               "/static/js/nowplaying.js",
               "/static/js/pro.js", "/static/js/serverwake.js",
               "/static/js/settings.js",
               "/static/js/strings.js", "/static/js/tts.js",
               "/static/js/util.js",
               "/static/js/wakeword.js"];
// Endpoint dinamici: mai in cache (lo stato del player cambia di continuo).
const NETWORK_ONLY = ["/nowplaying", "/artwork"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) {
    return; // i comandi (POST) e tutto il resto: sempre rete
  }
  if (NETWORK_ONLY.some((p) => url.pathname.startsWith(p))) {
    return; // stato live del player: sempre rete, mai cache
  }
  const isPage = url.pathname === "/" || url.pathname === "/index.html";
  if (isPage || url.pathname.startsWith("/static/")) {
    const key = isPage ? "/" : e.request;
    e.respondWith(
      fetch(e.request)
        .then((resp) => {
          // Solo una risposta BUONA sostituisce quella installata. Senza
          // questo controllo un 403 (host rifiutato da webguard), un 404 o un
          // 500 finivano in cache sotto "/" o sotto la chiave di un modulo:
          // l'app installata, riaperta offline, mostrava la pagina d'errore —
          // o un modulo il cui corpo è HTML servito come text/javascript,
          // cioè un'app bianca. Un errore è una risposta di adesso, non lo
          // stato dell'app da conservare.
          if (resp.ok) {
            const copy = resp.clone();
            // La put è asincrona e può fallire per conto suo (quota piena,
            // storage negato in navigazione privata): non deve trascinare
            // giù la risposta che stiamo già restituendo.
            caches.open(VERSION).then((c) => c.put(key, copy)).catch(() => {});
          }
          return resp;
        })
        // Offline: la copia in cache, se c'è.
        .catch(() => caches.match(key))
        // ...e se non c'è, un errore di rete. `caches.match` risolve a
        // `undefined` quando non trova nulla, e respondWith(undefined)
        // RIFIUTA con un TypeError invece di lasciar fallire la richiesta
        // come farebbe la rete: la pagina riceveva un errore che non
        // assomigliava a "sei offline" da nessuna parte.
        .then((resp) => resp || Response.error())
        .catch(() => Response.error())
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
