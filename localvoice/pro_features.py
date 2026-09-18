"""The Pro modules, and what the core does without them.

``licenses/README.md`` says everything but ``localvoice/pro/`` is AGPL-3.0 and
that the free half is a working program on its own. This module is where that
claim is kept. Every ``pro.*`` import the core makes outside the audio engines
is here, inside a function and guarded, and answers ``None`` when the package
is not there — which is the answer the Router, the HTTP handler and the setup
page were already written to accept: ``kidsafe=None`` and ``multiroom=None``
are how a build without a licence has always behaved.

Without the guard a checkout of the AGPL half alone did not start at all. It
raised ``ModuleNotFoundError: No module named 'pro'`` from the middle of
``server.main``, after the licence had been read and before the line that
would have said what was missing, and nothing downstream needed changing to
fix it — the imports simply had to be allowed to fail.

Inside a function rather than at module scope for the reason
``audio_engines.py`` gives for the same choice: these modules are cheap to
import and the packages behind them are not, and the guard has to run when the
feature is asked for rather than when this file is read.

The audio engines keep their own copies of this pattern, next to the printed
lines that explain each of them; ``tests/test_core_without_pro.py`` holds both
halves to it.
"""

from __future__ import annotations


def build_kidsafe(data_dir: str, license_mgr):
    """Kid-safe (Pro), or ``None`` when this build has no ``pro/``.

    The module lives in ``pro/`` and the core receives only the object and its
    small contract — ``enabled()``, ``terms()``, the PIN — never any blocking
    logic of its own.
    """
    try:
        from pro.kidsafe import KidSafe
    except ImportError:
        return None
    return KidSafe(data_dir, license_mgr)


def build_multiroom(license_mgr, client):
    """Multi-stanza (Pro), or ``None`` when this build has no ``pro/``.

    Come il kid-safe, il modulo vive in ``pro/`` e il core riceve solo
    l'oggetto col suo piccolo contratto — ``extract_room(text, lang)`` e
    ``pro_ok()``.
    """
    try:
        from pro.multiroom import MultiRoom
    except ImportError:
        return None
    return MultiRoom(license_mgr, client.get_players, lms=client)
