"""The language-pack registry and its contract (localvoice/lang/).

Adding a language is meant to be "drop one file in lang/": these tests are
what makes that safe — a pack that breaks the contract fails here with a
clear message, not in a routing step at runtime.
"""

import re

import pytest

import lang
from lang.base import c


def test_registry_finds_the_shipped_languages():
    assert set(lang.PACKS) >= {"it", "en", "de", "fr", "es"}


def test_helpers_are_not_mistaken_for_packs():
    # base.py has no CODE: the registry must skip it, not choke on it.
    assert all(hasattr(pack, "CODE") for pack in lang.PACKS.values())


@pytest.mark.parametrize("code", sorted(lang.PACKS))
def test_pack_honors_the_contract(code):
    pack = lang.PACKS[code]
    assert pack.CODE == code
    for attr in lang.REQUIRED:
        assert hasattr(pack, attr), f"{code} is missing {attr}"
    # The two service entries are templates (expanded per streaming service —
    # one for each word order, «da Qobuz metti X» and «metti X da Qobuz»);
    # every other pattern is compiled and ready.
    templates = ("service", "service_suffix")
    for key in templates:
        assert "{s}" in pack.PATTERNS[key], f"{code}.{key} is not a template"
    for key, pattern in pack.PATTERNS.items():
        if key not in templates:
            assert isinstance(pattern, re.Pattern), f"{code}.{key} not compiled"
    # DURATIONS: compiled regex + a spec the router understands.
    for pattern, spec in pack.DURATIONS:
        assert isinstance(pattern, re.Pattern)
        assert spec in ("hours", "minutes") or isinstance(spec, int)


def test_compile_helper_is_case_insensitive():
    assert c(r"^pausa$").match("PAUSA")


def test_message_catalogs_have_the_same_keys():
    # Every message is referenced by key from language-agnostic code (actions.py,
    # router.py); a key present in one catalog but not another would KeyError
    # only when that code path runs in the missing language.
    import messages
    keys = set(messages.IT)
    for code, catalog in messages.CATALOGS.items():
        assert set(catalog) == keys, f"{code} differs"


def test_every_language_pack_has_a_message_catalog():
    # The two halves of a language: a pack answers "what did they say", a
    # catalog "what do we say back". A pack without a catalog routes a
    # command and then KeyErrors on the reply.
    import messages
    assert set(lang.PACKS) == set(messages.CATALOGS)


def test_an_lms_failure_is_reported_in_the_language_of_the_turn():
    # matching.py used to freeze this sentence at import time, in whatever
    # DEFAULT_LANG happened to be, while every live path called msg() against
    # the per-request language. Nothing caught it because ActionResult
    # subclasses str: a comparison against the frozen constant came back False
    # rather than raising, so the tests that used it only passed while nobody
    # had switched language first.
    import actions
    import messages
    from lms import LMSClient, LMSError

    def dead(_params):
        raise LMSError("down")

    lms = LMSClient("http://lms:9000", "aa:bb", transport=dead)
    seen = {}
    for code in messages.CATALOGS:
        messages.set_lang(code)
        seen[code] = str(actions.pause(lms))
        assert seen[code] == messages.msg("err_unreachable")
    # ...and they really are different sentences, so the assertion above is
    # not comparing five copies of the Italian one.
    assert len(set(seen.values())) == len(messages.CATALOGS)
