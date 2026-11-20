"""Where each audiobook is, saved to Audiobookshelf every half minute (T5.6).

Audiobookshelf keeps the listening position, and its app and «riprendi il
libro X» both resume from it (T5.5). A book played on the hi-fi moves that
position only if somebody writes it, and the moment that matters most is
the one Vivavoce never hears about: music started from Material Skin, a
pause on the remote, a player switched off. So the position is not written
on the way out of a sentence but sampled, and a sample only ever loses the
last half minute.

What counts as "a book of ours, still playing" — and so what is safe to
write — is :meth:`player.composite.Composite.save_progress`'s to decide.
This module is only the clock, and it exists only with ``--library``.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

#: Seconds between two samples: the most of a book a switch can lose.
SAVE_EVERY = 30.0


def save_all(books: Any, failures: Optional[Dict[Any, str]] = None) -> None:
    """One round: save every player's book. A failure costs that player this
    round only — not the others, and not the loop.

    ``failures`` is the loop's memory of what is already broken, by player:
    an outage is logged when it starts and when it ends, not every round —
    the hi-fi switched off for the night is two lines, not a thousand.
    """
    failures = {} if failures is None else failures
    try:
        players = books.players()
    except Exception as exc:  # noqa: BLE001 — a thread nobody joins
        print(f"Audiobookshelf: il salvataggio del punto d'ascolto non è "
              f"partito ({exc}).")
        return
    for transport in players:
        try:
            books.save_progress(transport)
        except Exception as exc:  # noqa: BLE001 — a thread nobody joins
            # Anything uncaught here would end the thread in silence, and
            # every position after it would be lost the same way.
            # By kind, not by message: an open breaker's message counts down
            # («not dialled again for 12s»), and would be news every round.
            kind = type(exc).__name__
            if failures.get(transport) != kind:
                print(f"Audiobookshelf: non riesco a salvare il punto "
                      f"d'ascolto ({exc}); riprovo ogni {SAVE_EVERY:.0f} "
                      f"secondi, senza ripeterlo qui.")
            failures[transport] = kind
        else:
            if failures.pop(transport, None) is not None:
                print("Audiobookshelf: il punto d'ascolto si salva di nuovo.")


def start(books: Any, every: float = SAVE_EVERY,
          stop: Optional[Any] = None) -> threading.Thread:
    """Sample ``books`` every ``every`` seconds until ``stop`` is set, in a
    daemon thread: the server shutting down is what ends it. The first
    round waits too — at startup nothing is ours yet."""
    stop = stop if stop is not None else threading.Event()

    def loop() -> None:
        failures: Dict[Any, str] = {}
        while not stop.wait(every):
            save_all(books, failures)

    thread = threading.Thread(target=loop, name="book-progress", daemon=True)
    thread.start()
    return thread
