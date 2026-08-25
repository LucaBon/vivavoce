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


# Every runner label the workflow may use. An allowlist rather than a regex:
# a typo'd label doesn't fail loudly, the job just never gets picked up, and a
# green tick on a workflow that silently skipped a leg is the worst outcome
# available here.
KNOWN_RUNNERS = {"ubuntu-latest", "windows-latest", "ubuntu-24.04-arm"}


def _workflow_jobs(name="ci.yml"):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_read(".github", "workflows", name))["jobs"]


def _ci_jobs():
    return _workflow_jobs("ci.yml")


def _job_runners(job):
    """Every runner label a job can land on, matrix legs included."""
    matrix = job.get("strategy", {}).get("matrix", {})
    labels = list(matrix.get("os") or [])
    for leg in matrix.get("include", []):
        label = leg.get("os") or leg.get("runner")
        if label:
            labels.append(label)
    runs_on = job.get("runs-on", "")
    if "${{" not in runs_on:  # a literal label, not a matrix reference
        labels.append(runs_on)
    return labels


@pytest.mark.parametrize("workflow", ["ci.yml", "release.yml"])
def test_runner_labels_are_all_known(workflow):
    unknown = {label for job in _workflow_jobs(workflow).values()
               for label in _job_runners(job) if label not in KNOWN_RUNNERS}
    assert unknown == set(), f"unrecognised runner labels: {sorted(unknown)}"


# -- the published image -------------------------------------------------------
#
# DEPLOY.md offers a pull-and-run path and recommends a Raspberry Pi, so an
# image published for amd64 only would break the exact machine the docs push
# people towards — quietly, on their machine, at `docker run`. And a release
# workflow that publishes without checking would ship an image whose version
# label the code does not agree with: CI runs on branches, not tags, so this
# workflow is the only thing standing between a tag and a public artefact.

def test_the_release_workflow_publishes_both_architectures():
    build = _read(".github", "workflows", "release.yml")
    for arch in ("linux/amd64", "linux/arm64"):
        assert arch in build, f"the release image drops {arch}"


def test_the_release_workflow_is_triggered_by_version_tags():
    workflow = _read(".github", "workflows", "release.yml")
    yaml = pytest.importorskip("yaml")
    # PyYAML reads a bare `on:` key as the boolean True (the Norway problem).
    triggers = yaml.safe_load(workflow)
    on = triggers.get("on", triggers.get(True))
    assert "tags" in on["push"], "nothing ties the release to a tag"


def test_the_release_workflow_checks_the_tag_against_the_code():
    # The failure RELEASING.md is mostly about: two hand-edited copies of one
    # number, and a tag that has to match both.
    workflow = _read(".github", "workflows", "release.yml")
    assert "pyproject.toml" in workflow
    assert "tests/test_packaging.py" in workflow


def test_ci_proves_the_64_bit_claim_on_real_aarch64():
    # DEPLOY.md tells a Raspberry Pi 4/5 on a 64-bit image that both optional
    # engines work there. That started as an inference from wheels existing on
    # PyPI — necessary but not sufficient, since a wheel installing is not the
    # same as an ONNX model loading and scoring on that CPU. Each group now has
    # a job that runs it for real on aarch64, and deleting one has to fail here
    # rather than quietly turn a tested claim back into an assumed one.
    jobs = _ci_jobs()
    for group in SIXTY_FOUR_BIT_ONLY_GROUPS:
        assert group in jobs, f"no CI job named {group!r} to prove it"
        runners = _job_runners(jobs[group])
        assert any("arm" in label for label in runners), (
            f"the {group!r} job runs only on {runners}: nothing exercises the "
            f"aarch64 support DEPLOY.md promises")


def test_ci_runs_the_core_suite_on_aarch64():
    # The core is stdlib-only, so this should be indifferent to architecture —
    # which is exactly the kind of "should" worth one cheap job.
    runners = _job_runners(_ci_jobs()["test"])
    assert any("arm" in label for label in runners)


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


# -- file size -----------------------------------------------------------------
#
# "No file over 400 lines" was the acceptance criterion of two separate tasks
# (the index.html split, the server.py split), declared satisfied both times,
# and then nobody looked again: mic.js drifted back to 470 lines and
# http_api.py to 463 before anyone noticed. A rule no test checks is not a
# rule, so it is checked here — this module exists precisely for what the rest
# of the suite cannot see.
#
# Scope: the code that ships (engine/, localvoice/). Both original criteria
# were about runtime files, and that is where an unreadable module costs
# something. Tests and tools are deliberately out.

MAX_LINES = 400
SIZED_TREES = ("engine", "localvoice")
SIZED_SUFFIXES = (".py", ".js", ".html", ".css")

# Files already over the line when the rule got its test, each with the split
# that would fix it. A ratchet, not an amnesty: entries may leave this list,
# never join it — anything not named here has to be born under the limit.
OVERSIZED_TODAY = {
    "engine/actions.py",       # one class per intent family would halve it
    "engine/lms.py",           # transport, search and queue in one client
    "localvoice/router.py",    # the intent table has outgrown its module
}


def _sized_files():
    for tree in SIZED_TREES:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, tree)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if not name.endswith(SIZED_SUFFIXES):
                    continue
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, ROOT).replace(os.sep, "/"), full


def _line_count(path):
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


def test_no_source_file_is_oversized():
    too_big = {rel: _line_count(full) for rel, full in _sized_files()
               if rel not in OVERSIZED_TODAY and _line_count(full) > MAX_LINES}
    assert too_big == {}, (
        f"over {MAX_LINES} lines: {too_big} — split it, or (only with a reason) "
        f"add it to OVERSIZED_TODAY")


def test_the_oversized_list_only_shrinks():
    # The ratchet's other half: once a listed file is split, its entry has to
    # go, or the exemption outlives the problem and quietly permits a regrowth.
    files = dict(_sized_files())
    for rel in sorted(OVERSIZED_TODAY):
        assert rel in files, f"{rel} no longer exists: drop it from OVERSIZED_TODAY"
        assert _line_count(files[rel]) > MAX_LINES, (
            f"{rel} is now under {MAX_LINES} lines: drop it from OVERSIZED_TODAY "
            f"so it stays that way")
