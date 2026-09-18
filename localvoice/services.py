"""Which streaming services this install offers, and whether a typed list
is legal for the music system in front of us.

Split out of ``server.py``, which the 400-line rule caught when two branches
grew it at once. The seam is real rather than arithmetic: everything in
``server.py`` is *start-up wiring* — find the hi-fi, build the client, open
the socket — and this is the one question in it that is not wiring but
**judgement about configuration**, asked of the backend rather than of a table
here. It is the config-time half of what ``sources.py`` does at request time.
"""

from __future__ import annotations


def explicit_services(client, backend, spec: str):
    """``(services, complaint)`` for a ``--services`` list typed by hand.

    Which names are legal is a fact about the music system in front of us and
    not about LMS. A MusicAssistant provider domain is whatever that server
    has been configured with, so holding one against the LMS table rejected a
    perfectly good provider before the app had started once — and printed the
    LMS list of alternatives while doing it, which is the wrong list twice.

    A backend that has no services to speak of, or that would not answer, is
    taken at its word instead of being argued with: this branch is the escape
    hatch for when the detection misbehaves (see ``--services`` in
    ``cli.py``), and an escape hatch that needs the detection to work is not
    one. So an unanswerable question validates nothing rather than refusing
    everything.
    """
    services = [s.strip().lower() for s in spec.split(",") if s.strip()]
    # ``None`` is "nobody could be asked", which is NOT the empty list and was
    # read as it: a MusicAssistant with no providers answers ``[]``, so the old
    # ``if known else []`` accepted ``--services tidal`` unvalidated.
    known = None
    if backend.capabilities.services:
        try:
            known = client.known_services()
        except Exception:
            # Detto ad alta voce: da qui un token sbagliato e un server
            # occupato si assomigliano, e prendere la lista per buona in
            # silenzio manda a cercare il guasto dalla parte sbagliata.
            print("Non sono riuscito a chiedere all'impianto quali servizi ha: "
                  "prendo --services come l'hai scritto.")
    if known is None:  # niente da validare: la lista vale com'è scritta
        return (services, "") if services else ([], _bad_services(spec))
    if not services or [s for s in services if s not in known]:
        return [], _bad_services(spec, known)
    return services, ""


def _bad_services(spec: str, known=()) -> str:
    available = f" (disponibili: {', '.join(known)})" if known else ""
    return f"--services non valido: {spec!r}{available}"
