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
    assert set(lang.PACKS) >= {"it", "en"}


def test_helpers_are_not_mistaken_for_packs():
    # base.py has no CODE: the registry must skip it, not choke on it.
    assert all(hasattr(pack, "CODE") for pack in lang.PACKS.values())


@pytest.mark.parametrize("code", sorted(lang.PACKS))
def test_pack_honors_the_contract(code):
    pack = lang.PACKS[code]
    assert pack.CODE == code
    for attr in lang.REQUIRED:
        assert hasattr(pack, attr), f"{code} is missing {attr}"
    # The service entry is a template (expanded per streaming service), every
    # other pattern is compiled and ready.
    assert "{s}" in pack.PATTERNS["service"]
    for key, pattern in pack.PATTERNS.items():
        if key != "service":
            assert isinstance(pattern, re.Pattern), f"{code}.{key} not compiled"
    # DURATIONS: compiled regex + a spec the router understands.
    for pattern, spec in pack.DURATIONS:
        assert isinstance(pattern, re.Pattern)
        assert spec in ("hours", "minutes") or isinstance(spec, int)


def test_compile_helper_is_case_insensitive():
    assert c(r"^pausa$").match("PAUSA")
