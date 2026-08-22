"""Repo consistency: the things that break a release, not the code.

The suite proves the app works from a checkout. These check that what gets
shipped still matches it — a Dockerfile COPY that a file move stranded, or a
version bumped in one of the two places that declare it. Both fail in a user's
hands, not in a test run, so they are worth a cheap check on every push.

Stdlib only, so this runs locally as well as in CI.
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# -- the Docker image ----------------------------------------------------------

def _copy_sources(dockerfile):
    """Every local path a ``COPY`` instruction pulls into the image."""
    sources = []
    for line in dockerfile.splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        parts = line.split()[1:]
        parts = [p for p in parts if not p.startswith("--")]
        if len(parts) < 2:
            continue
        sources.extend(parts[:-1])  # the last argument is the destination
    return sources


def test_dockerfile_copies_paths_that_exist():
    # A moved or renamed file breaks `docker build` long after the tests pass.
    missing = [src for src in _copy_sources(_read("Dockerfile"))
               if not os.path.exists(os.path.join(ROOT, src))]
    assert missing == []


def test_dockerfile_copies_something():
    # Guards the parser itself: a COPY syntax it silently fails to read would
    # make the check above vacuously true.
    assert len(_copy_sources(_read("Dockerfile"))) >= 2


def test_addon_downloads_a_pinned_tag_not_a_branch():
    # The Supervisor passes BUILD_VERSION (the add-on version) and labels the
    # install with it, so the download has to resolve to exactly that release.
    # Fetching a branch instead would let two installs of the same "0.2.0" get
    # different sources as soon as the branch moves. CI builds the root
    # Dockerfile, not this one, so nothing else would notice the regression.
    dockerfile = _read("ha-addon", "Dockerfile")
    assert "refs/tags/v${BUILD_VERSION}" in dockerfile
    assert "refs/heads/" not in dockerfile


def test_addon_dockerfile_copies_paths_that_exist():
    # The Supervisor builds the add-on with ha-addon/ as the whole context, so
    # its COPY sources resolve against that directory, not the repo root.
    sources = _copy_sources(_read("ha-addon", "Dockerfile"))
    assert sources, "the add-on Dockerfile copies nothing"
    missing = [src for src in sources
               if not os.path.exists(os.path.join(ROOT, "ha-addon", src))]
    assert missing == []


# -- CPU architecture ----------------------------------------------------------
#
# Both optional engines rest on onnxruntime (openWakeWord directly,
# faster-whisper through CTranslate2), and neither has ever published a 32-bit
# wheel — not on PyPI, not on piwheels. So "armv7 is supported" and "the image
# installs an optional group" cannot both be true, and today they aren't: the
# add-on image installs neither group, which is exactly why it can honestly
# claim all three architectures. Adding one without dropping armv7 would ship
# an add-on that fails to build for a third of the machines it advertises,
# during a Supervisor build nothing in this repo would witness.

# The dependency groups whose wheels are 64-bit only (see pyproject.toml).
SIXTY_FOUR_BIT_ONLY_GROUPS = ("asr", "wakeword")
THIRTY_TWO_BIT_ARCHES = ("armv7", "armhf", "i386")


def _addon_arches():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_read("ha-addon", "config.yaml")).get("arch") or []


def test_addon_declares_only_arches_it_can_actually_build_for():
    dockerfile = _read("ha-addon", "Dockerfile")
    installs = [g for g in SIXTY_FOUR_BIT_ONLY_GROUPS
                if f"--group {g}" in dockerfile
                or re.search(rf"\b{g}\b.*==|pip install.*{g}", dockerfile)]
    declared_32bit = [a for a in _addon_arches() if a in THIRTY_TWO_BIT_ARCHES]
    assert not (installs and declared_32bit), (
        f"the add-on image installs {installs}, which has no 32-bit wheels, "
        f"while config.yaml still advertises {declared_32bit}: drop those "
        f"arches or drop the group")


def test_deploy_docs_state_the_64_bit_requirement():
    # The gap that prompted all of this: every other constraint was documented
    # with care (Python floor, why the groups are separate, what is untested)
    # and the architecture one was not, while four places advertise Raspberry
    # Pi. One marker per optional section, so a rewrite that drops the note
    # fails here rather than in a user's hands.
    deploy = _read("DEPLOY.md")
    assert deploy.count("Needs a 64-bit OS") == len(SIXTY_FOUR_BIT_ONLY_GROUPS)


# -- versions ------------------------------------------------------------------

def _pyproject_version():
    match = re.search(r'^version\s*=\s*"([^"]+)"', _read("pyproject.toml"),
                      re.M)
    assert match, "pyproject.toml declares no version"
    return match.group(1)


def _addon_version():
    match = re.search(r'^version:\s*"?([^"\s]+)"?\s*$',
                      _read("ha-addon", "config.yaml"), re.M)
    assert match, "ha-addon/config.yaml declares no version"
    return match.group(1)


def test_addon_version_matches_pyproject():
    # Two hand-edited copies of one number. The HA Supervisor compares its copy
    # against the installed one to decide whether an update exists, so a stale
    # add-on version ships an update nobody is offered.
    assert _addon_version() == _pyproject_version()


def test_changelog_documents_the_current_version():
    # The released version should have an entry to point users at.
    version = _pyproject_version()
    headings = re.findall(r"^##\s+(\S+)", _read("CHANGELOG.md"), re.M)
    assert version in headings


# -- the web assets ------------------------------------------------------------

def test_manifest_is_valid_json():
    # Served verbatim; a trailing comma makes the app un-installable.
    manifest = json.loads(_read("localvoice", "manifest.webmanifest"))
    assert manifest["icons"]


def test_manifest_icons_exist_on_disk():
    manifest = json.loads(_read("localvoice", "manifest.webmanifest"))
    for icon in manifest["icons"]:
        path = os.path.join(ROOT, "localvoice", icon["src"].lstrip("/"))
        assert os.path.exists(path), f"missing icon file: {icon['src']}"


def test_service_worker_shell_assets_exist_on_disk():
    match = re.search(r"const SHELL = \[(.*?)\]", _read("localvoice", "sw.js"),
                      re.S)
    assert match
    for path in re.findall(r'"([^"]+)"', match.group(1)):
        if path == "/":  # the page itself, not a file
            continue
        assert os.path.exists(os.path.join(ROOT, "localvoice", path.lstrip("/")))


# -- the deploy descriptors ----------------------------------------------------

DEPLOY_YAML = [
    ("ha-addon", "config.yaml"),
    ("ha-addon", "build.yaml"),
    ("repository.yaml",),
    ("docker-compose.yml",),
]


@pytest.mark.parametrize("parts", DEPLOY_YAML,
                         ids=[p[-1] if len(p) == 1 else "/".join(p)
                              for p in DEPLOY_YAML])
def test_deploy_yaml_parses(parts):
    # Skips rather than fails without PyYAML: the suite is stdlib-only by
    # design, and CI installs the dev group.
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(_read(*parts)) is not None
