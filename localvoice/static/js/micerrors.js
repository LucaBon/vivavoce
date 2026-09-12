// Why the microphone stopped, in words rather than in the browser's code.
//
// A status line reading "Microphone error: audio-capture" tells a household
// nothing they can act on, and "Continuous listening stopped (network)" tells
// them less than that. The Web Speech API and getUserMedia raise a small,
// fixed vocabulary of codes, and every one of them has a thing the person in
// front of the phone could actually do about it.
//
// Kept apart from strings.js because it is the one table keyed by somebody
// else's words: it changes when a browser invents a code, not when we write
// a new sentence.

export const MIC_WHY_EN = {
  "not-allowed": "the microphone permission was refused, or the prompt was " +
    "dismissed. Allow it for this page in the browser's site settings.",
  "service-not-allowed": "the browser blocked its speech service for this " +
    "page. Allow the microphone in the site settings.",
  NotAllowedError: "the microphone permission was refused, or the prompt was " +
    "dismissed. Allow it for this page in the browser's site settings.",
  "audio-capture": "no microphone was available. Check one is connected and " +
    "not in use by another app.",
  NotFoundError: "this device has no microphone the browser can use.",
  NotReadableError: "the microphone is busy in another app. Close it and try " +
    "again.",
  network: "the browser could not reach its speech service. Check this " +
    "device's internet connection, or switch on local recognition.",
  "no-speech": "nothing was heard.",
  aborted: "listening was interrupted.",
  "language-not-supported": "this browser does not recognise the language " +
    "picked in settings. Choose another in Settings.",
};

export const MIC_WHY_IT = {
  "not-allowed": "il permesso per il microfono è stato negato, o la richiesta " +
    "è stata chiusa. Concedilo a questa pagina nelle impostazioni del sito.",
  "service-not-allowed": "il browser ha bloccato il suo servizio vocale per " +
    "questa pagina. Concedi il microfono nelle impostazioni del sito.",
  NotAllowedError: "il permesso per il microfono è stato negato, o la " +
    "richiesta è stata chiusa. Concedilo a questa pagina nelle impostazioni " +
    "del sito.",
  "audio-capture": "nessun microfono disponibile. Controlla che ce ne sia uno " +
    "collegato e non occupato da un'altra app.",
  NotFoundError: "questo dispositivo non ha un microfono utilizzabile dal " +
    "browser.",
  NotReadableError: "il microfono è occupato da un'altra app. Chiudila e " +
    "riprova.",
  network: "il browser non è riuscito a raggiungere il suo servizio vocale. " +
    "Controlla la connessione di questo dispositivo, oppure attiva il " +
    "riconoscimento locale.",
  "no-speech": "non ho sentito niente.",
  aborted: "l'ascolto è stato interrotto.",
  "language-not-supported": "questo browser non riconosce la lingua scelta " +
    "nelle impostazioni. Scegline un'altra.",
};

/** The code as a sentence, or the bare code in brackets when unknown.
 *
 * Unknown codes keep their raw spelling rather than getting a generic
 * "something went wrong": an unexplained code is still a thing to search
 * for, and a confident wrong explanation is not.
 */
export function micWhy(table, code) {
  const key = (code && (code.name || code.error || code)) + "";
  return table[key] || "(" + key + ")";
}
