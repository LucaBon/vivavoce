"""Repo consistency: the things that break a release, not the code.

The suite proves the app works from a checkout. These check that what gets
shipped still matches it — a Dockerfile COPY that a file move stranded, or a
version bumped in one of the two places that declare it. Both fail in a user's
hands, not in a test run, so they are worth a cheap check on every push.

Stdlib only, so this runs locally as well as in CI.
"""

import ast
import json
import os
import re
import shutil
import struct
import subprocess
import sys

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
# The add-on is 64-bit only since Home Assistant dropped 32-bit with 2025.12
# (ha-addon/config.yaml says why at length). That settled a tension rather
# than removing the need for this check: faster-whisper reaches onnxruntime
# through CTranslate2, and neither has ever published a 32-bit wheel — not on
# PyPI, not on piwheels — so "armv7 is supported" and "the image installs the
# asr group" could never both be true. While armv7 was declared, the second
# one was the half that gave way.
#
# It binds in the other direction now, which is why it stays: a 32-bit arch
# put back into config.yaml while the image bakes in asr would ship an add-on
# that fails to build for the machines it advertises, during a Supervisor
# build nothing in this repo would witness.
#
# Which half would give way today is moot, though, because the image cannot
# bake in asr on any architecture: it is Alpine, and neither CTranslate2 nor
# onnxruntime publishes a musllinux wheel — pip finds none even on amd64, even
# with Home Assistant's own musl index already in the chain, and Alpine
# packages neither. That is a libc limit and not an architecture one, so
# dropping armv7 did not lift it. The check costs nothing and outlives its
# reason: it is already here on the day a musl wheel appears, or the day
# somebody adds an arch.
#
# `wakeword-vosk` is deliberately NOT in this list and must not be added to
# it: vosk publishes a py3-none-linux_armv7l wheel, so it is the one optional
# group a 32-bit Pi can install — over the source or self-built Docker route,
# which is not the add-on and keeps its own 32-bit story in DEPLOY.md. It was
# `wakeword` (openWakeWord, retired) that belonged here.

# The dependency groups whose wheels are 64-bit only (see pyproject.toml).
SIXTY_FOUR_BIT_ONLY_GROUPS = ("asr",)
# Every optional engine, whatever its word size — a different question, and
# the reason the two lists are not one: this one asks "is the aarch64 support
# DEPLOY.md promises actually exercised", which `wakeword-vosk` needs answered
# just as much even though it also installs on armv7.
OPTIONAL_ENGINE_GROUPS = ("asr", "wakeword-vosk")
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
KNOWN_RUNNERS = {"ubuntu-latest", "windows-latest", "ubuntu-24.04-arm",
                 "macos-latest"}


def _workflow_jobs(name="ci.yml"):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_read(".github", "workflows", name))["jobs"]


def _ci_jobs():
    return _workflow_jobs("ci.yml")


def _job_runners(job):
    """Every runner label a job can land on, matrix legs included."""
    matrix = job.get("strategy", {}).get("matrix", {})
    labels = list(matrix.get("os") or [])
    # `include` may be a `${{ fromJSON(...) }}` expression rather than a list —
    # the add-on jobs build theirs from ha-addon/config.yaml. Those legs carry
    # no runner label anyway: the job's own `runs-on` is the whole answer.
    include = matrix.get("include")
    for leg in include if isinstance(include, list) else []:
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


# -- the linter exists, and runs ----------------------------------------------
#
# ``engine/actions.py`` carried a file-level ruff suppression, and the project
# memory said the lint command was ``ruff check`` — while ruff was in no
# dependency group and in no CI job, so ``uv run ruff check`` answered
# "command not found". A reference to a tool nobody can run is worse than no
# tool: it reads as a checked invariant and is not one. These two are what
# make it a fact.

def test_the_linter_is_a_dependency_and_is_configured():
    pyproject = _read("pyproject.toml")
    assert '"ruff' in pyproject, "ruff is referenced in the repo but not installed"
    assert "[tool.ruff]" in pyproject, "ruff would run with nothing configured"


def test_ci_actually_runs_the_linter():
    steps = [step for job in _ci_jobs().values()
             for step in job.get("steps", [])]
    assert any("ruff check" in (step.get("run") or "") for step in steps), (
        "no CI job runs the linter, so a violation reaches main unnoticed")


# -- the browser suite actually running ----------------------------------------
#
# The failure this guards is one that already happened, unnoticed, for as long
# as nobody looked: `playwright install` exits 0 when it fails, so a broken
# install leaves a green job in which all 24 browser tests skipped. Since that
# directory is the only thing checking the page's JS wiring, the tick would
# have meant nothing. VIVAVOCE_REQUIRE_BROWSER=1 turns those skips into
# failures (see tests/e2e/conftest.py) — and this makes sure CI keeps setting
# it, because a safety net nobody checks is how the first one was lost.

def test_ci_requires_the_browser_suite_to_really_run():
    steps = _ci_jobs()["e2e"]["steps"]
    setting = [step for step in steps
               if step.get("env", {}).get("VIVAVOCE_REQUIRE_BROWSER") == "1"]
    assert setting, ("the e2e job does not set VIVAVOCE_REQUIRE_BROWSER=1: a "
                     "missing browser would skip every test and still pass")
    assert any("pytest" in str(step.get("run", "")) for step in setting), (
        "VIVAVOCE_REQUIRE_BROWSER=1 is set on a step that does not run pytest")


def test_ci_proves_the_browser_launches_rather_than_trusting_the_installer():
    # `playwright install` returning 0 is not evidence. Launching one is.
    runs = " ".join(str(step.get("run", "")) for step in _ci_jobs()["e2e"]["steps"])
    assert "chromium.launch()" in runs, (
        "nothing in the e2e job checks that a browser can actually start")


def test_ci_has_a_fallback_for_platforms_playwright_does_not_know_yet():
    # Ubuntu 26.04 already refuses; ubuntu-latest will get there.
    runs = " ".join(str(step.get("run", "")) for step in _ci_jobs()["e2e"]["steps"])
    assert "PLAYWRIGHT_HOST_PLATFORM_OVERRIDE" in runs


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
    # DEPLOY.md tells a Raspberry Pi 4/5 on a 64-bit image that the optional
    # engines work there. That started as an inference from wheels existing on
    # PyPI — necessary but not sufficient, since a wheel installing is not the
    # same as a model loading and scoring on that CPU. Each group now has a job
    # that runs it for real on aarch64, and deleting one has to fail here
    # rather than quietly turn a tested claim back into an assumed one.
    jobs = _ci_jobs()
    for group in OPTIONAL_ENGINE_GROUPS:
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


# -- the Home Assistant add-on image -------------------------------------------
#
# The `docker` job builds the standalone image. The add-on image is a separate
# artefact with almost nothing in common — Alpine bases published by the
# Supervisor instead of python:3.12-slim, `apk add` instead of pip, source
# downloaded from a tag instead of copied from the checkout — and until the
# `addon` job existed nothing built it, on any architecture. So the reasoning
# in test_addon_declares_only_arches_it_can_actually_build_for rested on an
# argument no build had ever checked — and the architecture it was reasoning
# about, armv7, turned out to have been frozen upstream since 2025 and is no
# longer declared at all.
#
# What the job can prove on a branch is bounded, and the bound is the point:
# BUILD_VERSION is the newest existing tag, not the declared version, because
# between releases `develop` declares a version that is deliberately not
# tagged yet. See the job's own comment.


# Both workflows build the add-on image, and neither one says how. The steps
# live in a composite action and the architecture list is derived from the
# add-on's own descriptors, so the two jobs differ in exactly one thing: which
# version they build. These check that it stays that way — a step copied back
# into a workflow, or a matrix written out by hand, is how the two drift apart
# again, and the second copy is always the one nobody updates.

ADDON_WORKFLOWS = ("ci.yml", "release.yml")
ADDON_ACTION = (".github", "actions", "addon-image", "action.yml")
MATRIX_SCRIPT = "tools/ci_addon_matrix.py"


def _addon_job(workflow="ci.yml"):
    return _workflow_jobs(workflow)["addon"]


def _addon_job_script(workflow="ci.yml"):
    return " ".join(str(step.get("run", ""))
                    for step in _addon_job(workflow)["steps"])


def _addon_action():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_read(*ADDON_ACTION))


def _addon_action_script():
    return " ".join(str(step.get("run", ""))
                    for step in _addon_action()["runs"]["steps"])


def _matrix_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ci_addon_matrix", os.path.join(ROOT, *MATRIX_SCRIPT.split("/")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_declared_addon_arch_has_a_base_image():
    # config.yaml advertises the arches; build.yaml says what each one is built
    # from. An arch in the first and not the second is an add-on the Supervisor
    # offers and then cannot build.
    yaml = pytest.importorskip("yaml")
    build_from = yaml.safe_load(_read("ha-addon", "build.yaml"))["build_from"]
    missing = [a for a in _addon_arches() if a not in build_from]
    assert missing == [], f"no build_from entry for {missing} in build.yaml"


def test_the_matrix_script_reads_the_same_files_pyyaml_does():
    # The script parses config.yaml and build.yaml by hand, because the job
    # that runs it installs no dependencies (see its docstring). This is what
    # keeps that honest: the real YAML parser, on the same two files, has to
    # give the same answer. A shape the narrow parser cannot read fails here
    # rather than silently building fewer architectures.
    yaml = pytest.importorskip("yaml")
    module = _matrix_module()
    assert module.declared_arches() == _addon_arches()
    assert module.base_images() == yaml.safe_load(
        _read("ha-addon", "build.yaml"))["build_from"]


def test_the_matrix_covers_every_declared_arch():
    legs = _matrix_module().matrix()
    assert [leg["arch"] for leg in legs] == _addon_arches()
    for leg in legs:
        assert leg["platform"] and leg["machine"] and leg["base"]


def test_the_matrix_refuses_an_arch_it_has_no_platform_for(monkeypatch):
    # The one way adding an arch to config.yaml can go wrong now: a name this
    # script has no Docker platform for. It has to stop, not emit a leg with
    # an empty platform that buildx would read as "the host architecture" —
    # which is a green ARM job that ran on x86, the exact thing being guarded
    # against everywhere else here.
    module = _matrix_module()
    monkeypatch.setattr(module, "declared_arches", lambda: ["sparc64"])
    with pytest.raises(SystemExit):
        module.matrix()


@pytest.mark.parametrize("workflow", ADDON_WORKFLOWS)
def test_the_addon_matrix_is_derived_not_written_out(workflow):
    text = _read(".github", "workflows", workflow)
    assert MATRIX_SCRIPT in text, (
        f"{workflow} no longer derives the add-on architectures from "
        f"{MATRIX_SCRIPT}: a hand-written matrix is a second copy of a list "
        f"that already exists in ha-addon/config.yaml")
    include = _addon_job(workflow)["strategy"]["matrix"]["include"]
    assert "fromJSON" in str(include), (
        f"the addon matrix in {workflow} is written out by hand")


@pytest.mark.parametrize("workflow", ADDON_WORKFLOWS)
def test_the_addon_is_built_through_the_shared_action(workflow):
    uses = [step.get("uses", "") for step in _addon_job(workflow)["steps"]]
    assert "./.github/actions/addon-image" in uses, (
        f"the addon job in {workflow} no longer goes through the shared "
        f"action: its steps were the thing duplicated between the two")


@pytest.mark.parametrize("workflow", ADDON_WORKFLOWS)
def test_no_workflow_hardcodes_an_add_on_base_image(workflow):
    # RELEASING.md is mostly the story of one number living in several
    # hand-edited places. The base images are not going to become the next one.
    for text, where in ((_read(".github", "workflows", workflow), workflow),
                        (_read(*ADDON_ACTION), "the shared action")):
        hardcoded = re.findall(r"ghcr\.io/home-assistant/\S+-base:\S+", text)
        assert hardcoded == [], (
            f"{where} hardcodes {hardcoded} instead of taking it from "
            f"ha-addon/build.yaml")


def test_the_addon_action_starts_the_image_it_builds():
    # The same distinction the e2e job makes about `playwright install`: a
    # build proves the layers assemble, and the thing most likely to be wrong
    # on a foreign architecture is a native library, which only fails when it
    # runs. py3-cryptography generating the first certificate is that check.
    script = _addon_action_script()
    assert "docker run" in script, (
        "the shared action builds an image nobody starts: a native library for "
        "the wrong architecture would sail through a build-only job")
    assert "/data/cert.pem" in script, (
        "nothing checks that the certificate was generated, which is the only "
        "step that makes py3-cryptography actually execute")


def test_the_addon_action_checks_it_really_ran_on_that_architecture():
    # Without this the ARM legs could run on x86 and still go green.
    assert "uname -m" in _addon_action_script()


def test_the_addon_action_checks_the_image_carries_the_version_asked_for():
    # A tag pointing at the wrong commit builds fine and produces an image
    # whose pyproject says something else. Read back from inside the image,
    # because the point is what the tarball contained, not what the checkout
    # says.
    assert "/app/pyproject.toml" in _addon_action_script(), (
        "nothing reads the version back out of the built add-on image")


#: The newest version tag that exists, looked up without a pipe (see
#: test_no_step_pipes_into_a_reader_that_stops_early).
NEWEST_TAG = re.compile(r"git for-each-ref --count=1 --sort=-v:refname"
                        r"[\s\S]*?'refs/tags/v\[0-9\]")


def test_ci_builds_the_addon_from_a_tag_that_exists_not_the_declared_one():
    # Deliberate, and easy to "fix" into a job that is red on develop for most
    # of every release cycle: the Dockerfile 404s on an untagged version, and
    # an untagged version is the normal state of develop between releases.
    assert NEWEST_TAG.search(_addon_job_script("ci.yml")), (
        "the ci.yml addon job no longer derives BUILD_VERSION from an existing "
        "tag; building the declared version fails on develop by design")


def test_the_release_builds_the_addon_from_the_tag_being_released():
    # And the converse, which is the whole reason this job exists next to the
    # ci.yml one: on a tag the version is not a fallback, it is the release.
    # This is the only place the exact tarball a Supervisor will download is
    # ever built before someone installs it.
    #
    # The branch is what gets asserted, not the string "refs/tags/": that
    # appears in the expansion too, so a job that had stopped taking the tag
    # branch at all still read as if it did.
    script = _addon_job_script("release.yml")
    assert re.search(r"refs/tags/\*\s*\)", script), (
        "nothing in the release addon job branches on being run from a tag, "
        "so it cannot be building the version being released")
    assert "GITHUB_REF#refs/tags/v" in script, (
        "the release addon job does not take BUILD_VERSION from the tag")
    assert NEWEST_TAG.search(script), (
        "no fallback for workflow_dispatch, where there is no tag: the note at "
        "the top of release.yml promises a manual run exercises the workflow")


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


# Every doc that tells someone which image tag to run. An explicit list, like
# the price and descriptor checks below: analysis records under docs/ quote
# versions as findings dated to the day they were written, and freezing those
# would be wrong.
VERSIONED_DOCS = [("DEPLOY.md",),
                  ("README.md",),
                  ("RELEASING.md",),
                  ("ha-addon", "DOCS.md"),
                  ("ha-addon", "README.md")]

# `ghcr.io/lucabon/vivavoce:0.2.0` and the bare backticked pin DEPLOY.md
# recommends (`` `:0.2.0` ``). Deliberately not a loose ":X.Y" — the release
# instructions also quote Home Assistant's own base image tag, which is not
# ours to keep in step, and neither is `amd64-base:3.23` in build.yaml.
#
# The backtick has to be the one that OPENS the span, not any closing one,
# and the two are told apart by what precedes it rather than what follows:
# in `` `:0.2.0` `` and in `` `python`:3.9 `` the backtick is followed by a
# colon either way. A pin's backtick opens after a space or a bracket; a
# closing one comes straight off a word. Nothing in the repo is written the
# second way today, which is exactly when a regex is cheap to tighten.
CITED_TAG = re.compile(r"(?:vivavoce:|(?<!\w)`:)(\d+\.\d+(?:\.\d+)?)\b")


@pytest.mark.parametrize("parts", VERSIONED_DOCS,
                         ids=[p[-1] if len(p) == 1 else "/".join(p)
                              for p in VERSIONED_DOCS])
def test_docs_quote_the_declared_version(parts):
    # The third hand-edited copy of the number, and the one nothing watched:
    # DEPLOY.md recommended pinning `:0.3.0` for months while both version
    # files said 0.2.0 and no such tag had ever been pushed. That advice does
    # not fail here, it fails at `docker pull` — with a manifest-unknown error
    # — on the machine of someone following the install guide to the letter.
    #
    # Named for what it checks, which is narrower than "a version that
    # exists": it pins the docs to the version DECLARED in pyproject.toml.
    # Between step 1 of RELEASING.md (the bump) and step 5 (the image is
    # published) that version is deliberately one nobody can pull yet, and
    # this test wants the docs to move with the bump — so the two agree at
    # the end of a release rather than at every instant during one.
    version = _pyproject_version()
    series = ".".join(version.split(".")[:2])
    for cited in CITED_TAG.findall(_read(*parts)):
        expected = series if cited.count(".") == 1 else version
        assert cited == expected, (
            f"{parts[-1]} recommends the image tag :{cited}, but the version "
            f"is {version}: either the docs are ahead of a release that never "
            f"happened, or a bump forgot them")


def test_the_install_guide_quotes_a_tag_at_all():
    # Guards the check above from going vacuous: it only fails on a citation
    # it can find, so a reworded pin line it no longer matches would turn the
    # whole thing green while saying nothing.
    assert CITED_TAG.findall(_read("DEPLOY.md")), (
        "DEPLOY.md quotes no image tag any more: either the pin advice went "
        "away, or CITED_TAG stopped recognising how it is written")


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


# -- the Home Assistant store page ---------------------------------------------
#
# The app is a declared distribution channel (decided 2026-08-26, see the
# roadmap): the blueprint route into Home Assistant needs the Vivavoce server
# running next to it, and this is the one-click way to get there. What the
# Supervisor shows for it is three files beside config.yaml, none of which the
# build would miss: without an icon the store draws a generic placeholder, and
# nothing anywhere fails.

def _png_size(*parts):
    """(width, height) from a PNG's IHDR — stdlib, no Pillow, like the tool
    that writes these files (tools/make_icons.py)."""
    with open(os.path.join(ROOT, *parts), "rb") as f:
        header = f.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{parts[-1]} is not a PNG"
    assert header[12:16] == b"IHDR", f"{parts[-1]} does not start with IHDR"
    return struct.unpack(">II", header[16:24])


def test_the_addon_ships_the_store_artwork():
    # Home Assistant requires the PNG format and these exact filenames. Both
    # halves are checked: existence caught a missing file, but a logo.png that
    # was a text file or a GIF passed happily, and the format is the part the
    # docs make a requirement rather than a recommendation.
    for name in ("icon.png", "logo.png"):
        path = os.path.join(ROOT, "ha-addon", name)
        assert os.path.exists(path), (
            f"ha-addon/{name} is missing: the store falls back to a generic "
            f"placeholder and nothing else complains")
        width, height = _png_size("ha-addon", name)
        assert width > 0 and height > 0, f"ha-addon/{name} has no size"


def test_the_addon_icon_is_square():
    # A requirement, not a recommendation: the docs ask for a 1x1 aspect
    # ratio (128x128 is the suggested size). Regenerate with
    # `uv run python tools/make_icons.py`.
    width, height = _png_size("ha-addon", "icon.png")
    assert width == height, f"ha-addon/icon.png is {width}x{height}, not square"


# -- the container healthcheck -------------------------------------------------
#
# The probe is a one-liner inside the Dockerfile, so nothing imports it and no
# test could see it. It has to agree with deploy/docker/entrypoint.sh about
# which variables name the port and the scheme — and it did not: it read only
# the VIVAVOCE_* names while the entrypoint still falls back to SQUEEZESAY_*,
# so an upgraded container could serve HTTP while the probe demanded HTTPS.


def _healthcheck_probe():
    """The python source of the HEALTHCHECK CMD, lifted from the Dockerfile."""
    text = _read("Dockerfile").replace("\\\n", "")
    match = re.search(r'HEALTHCHECK[^\n]*?CMD python -c "(.*?)"\n', text, re.S)
    assert match, "HEALTHCHECK shape changed — this test cannot find the probe"
    return match.group(1)


def _probe_decides(env):
    """Run the probe's decision half under ``env``; return (port, scheme).

    The real os.environ, swapped and restored: the probe opens with its own
    ``import os``, so a stand-in object passed through the namespace would be
    replaced by the genuine module on the first statement.
    """
    source = _healthcheck_probe()
    # Everything up to the urlopen: the request itself needs a live server,
    # the choice of what to request is what has to be right.
    decision = source.split("ctx=")[0]
    saved = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(env)
        namespace = {}
        exec(decision, namespace)      # noqa: S102 - our own Dockerfile
        return namespace["port"], namespace["scheme"]
    finally:
        os.environ.clear()
        os.environ.update(saved)


@pytest.mark.parametrize("env, expected", [
    ({}, ("8730", "https")),
    ({"VIVAVOCE_HTTPS": "0"}, ("8730", "http")),
    ({"VIVAVOCE_PORT": "9000"}, ("9000", "https")),
    # The names one release of docker-compose.yml still advertises.
    ({"SQUEEZESAY_HTTPS": "0"}, ("8730", "http")),
    ({"SQUEEZESAY_PORT": "9000"}, ("9000", "https")),
    # And the new name wins where both are set, as in the entrypoint.
    ({"SQUEEZESAY_HTTPS": "0", "VIVAVOCE_HTTPS": "1"}, ("8730", "https")),
    ({"SQUEEZESAY_PORT": "9000", "VIVAVOCE_PORT": "9001"}, ("9001", "https")),
])
def test_the_healthcheck_reads_the_same_variables_as_the_entrypoint(env, expected):
    assert _probe_decides(env) == expected


def test_the_healthcheck_knows_every_name_the_entrypoint_falls_back_to():
    # If the entrypoint grows another legacy fallback for the port or the
    # scheme, the probe has to learn it in the same commit.
    entrypoint = _read("deploy", "docker", "entrypoint.sh")
    probe = _healthcheck_probe()
    for line in entrypoint.splitlines():
        if line.startswith(("PORT=", "HTTPS=")):
            for name in re.findall(r"[A-Z][A-Z0-9_]*(?=[:}])", line):
                assert name in probe, (
                    f"{name} is read by the entrypoint but not by the "
                    f"HEALTHCHECK, so the probe can disagree with the server")


# -- the add-on's option reader ------------------------------------------------
#
# run.sh translates /data/options.json into the VIVAVOCE_* variables the shared
# entrypoint reads. It is shell, so nothing else in this suite can see it, and
# the one bug it had was invisible by inspection: jq's `//` treats a JSON false
# exactly like a missing key, so the only boolean option we expose was read as
# "unset" and silently ignored.

_RUN_SH_NEEDS = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("jq") or not shutil.which("sh"),
    reason="needs a POSIX sh and jq, as the add-on image has")


def _run_addon_script(tmp_path, options):
    """Run the real ha-addon/run.sh against ``options``, return its exported env.

    The script is copied with two lines rewritten: the hard-coded options path,
    and the exec of the entrypoint (which would start a server) swapped for a
    dump of the environment. Everything between them — the part under test —
    is the shipped file.
    """
    opts = tmp_path / "options.json"
    opts.write_text(json.dumps(options), encoding="utf-8")
    script = _read("ha-addon", "run.sh")
    script = script.replace("OPTS=/data/options.json", f'OPTS="{opts}"')
    script = script.replace("exec /app/deploy/docker/entrypoint.sh", "exec env")
    assert 'OPTS="' in script and "exec env" in script, "run.sh shape changed"
    runner = tmp_path / "run.sh"
    runner.write_text(script, encoding="utf-8")
    out = subprocess.run(["sh", str(runner)], capture_output=True, text=True,
                         timeout=30, check=True).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


@_RUN_SH_NEEDS
def test_https_false_is_honoured_not_swallowed(tmp_path):
    # `https: false` is documented in DOCS.md as "solo HTTP". It reached the
    # entrypoint as nothing at all, which falls back to HTTPS=1: the add-on
    # served TLS whatever the user chose, and an ingress or reverse proxy in
    # front of it speaking plain HTTP got a protocol error for its trouble.
    env = _run_addon_script(tmp_path, {"https": False, "port": 8730})
    assert env.get("VIVAVOCE_HTTPS") == "0"
    assert env.get("VIVAVOCE_PORT") == "8730"


@_RUN_SH_NEEDS
@pytest.mark.parametrize("options", [{"https": True}, {}, {"port": 8730}])
def test_https_is_left_alone_unless_it_is_false(options, tmp_path):
    # Only an explicit false turns TLS off; absent or true keep the default,
    # which the entrypoint supplies rather than this script.
    assert "VIVAVOCE_HTTPS" not in _run_addon_script(tmp_path, options)


@_RUN_SH_NEEDS
def test_the_string_options_still_reach_the_entrypoint(tmp_path):
    # The same helper reads every other option; changing how it handles false
    # must not change how it handles the strings around it.
    env = _run_addon_script(tmp_path, {
        "port": 9000, "lms_url": "http://lms.local:9000", "player": "Cucina",
        "cert_hosts": "vivavoce.local", "material_url": "http://m.local",
    })
    assert env["VIVAVOCE_PORT"] == "9000"
    assert env["VIVAVOCE_LMS"] == "http://lms.local:9000"
    assert env["VIVAVOCE_PLAYER"] == "Cucina"
    assert env["VIVAVOCE_CERT_HOSTS"] == "vivavoce.local"
    assert env["VIVAVOCE_MATERIAL_URL"] == "http://m.local"
    assert env["VIVAVOCE_DATA_DIR"] == "/data"


@_RUN_SH_NEEDS
def test_a_token_never_travels_on_the_command_line(tmp_path):
    """The command line of a process is readable by anyone who can run `ps` —
    in the container, and from the host for the namespaces that allow it — and
    it ends up in debug dumps and crash reports. ``cli.py`` reads every token
    from the environment, which the entrypoint already has, so passing them as
    arguments as well only published them.
    """
    entrypoint = _read("deploy", "docker", "entrypoint.sh")
    for flag in ("--backend-token", "--library-token", "--api-token"):
        assert flag not in entrypoint, f"{flag} finisce nella riga di comando"
    # And they still arrive, by the other road.
    env = _run_addon_script(tmp_path, {"backend_token": "b3", "library_token": "l1"})
    assert env["VIVAVOCE_BACKEND_TOKEN"] == "b3"
    assert env["VIVAVOCE_LIBRARY_TOKEN"] == "l1"


@_RUN_SH_NEEDS
def test_the_library_options_reach_the_entrypoint(tmp_path):
    # Three options, three exports: an option the add-on UI offers and
    # nothing forwards is a setting that silently does nothing. Two of them
    # travel on to the server as flags; the token takes the other road, and
    # the test below is the one that says so.
    env = _run_addon_script(tmp_path, {
        "library": "audiobookshelf", "library_url": "http://books.local:13378",
        "library_token": "k3y",
    })
    assert env["VIVAVOCE_LIBRARY"] == "audiobookshelf"
    assert env["VIVAVOCE_LIBRARY_URL"] == "http://books.local:13378"
    assert env["VIVAVOCE_LIBRARY_TOKEN"] == "k3y"
    entrypoint = _read("deploy", "docker", "entrypoint.sh")
    for flag in ("--library", "--library-url"):
        assert f'set -- "$@" {flag} ' in entrypoint, f"entrypoint drops {flag}"
    yaml = pytest.importorskip("yaml")
    schema = yaml.safe_load(_read("ha-addon", "config.yaml"))["schema"]
    # The key is a secret: "password" keeps it out of the options panel and
    # the Supervisor's logs, like backend_token.
    assert schema["library_token"] == "password?"


@_RUN_SH_NEEDS
def test_an_empty_string_option_is_not_exported(tmp_path):
    # An option left blank in the add-on UI must not become an empty setting
    # the app then tries to use as a URL.
    env = _run_addon_script(tmp_path, {"lms_url": "", "player": ""})
    assert "VIVAVOCE_LMS" not in env
    assert "VIVAVOCE_PLAYER" not in env


def test_the_addon_has_its_own_changelog():
    # The root changelog is the project's, written for everyone; this one is
    # for the person updating the app, and lives beside config.yaml because
    # that is where the documentation says to put it.
    changelog = _read("ha-addon", "CHANGELOG.md")
    assert f"[{_addon_version()}]" in changelog, (
        f"ha-addon/CHANGELOG.md has no entry for {_addon_version()}")


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
# Vuota, e il test qui sotto la tiene vuota: l'ultima voce era engine/lms.py,
# 1317 righe di client, e ora è sei file — il client, la tabella dei servizi,
# e un mixin per ciascuna delle quattro cose che quel client sa fare.
OVERSIZED_TODAY = set()


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


# -- the launch material -------------------------------------------------------
#
# The price is quoted in three files written at different times, in two
# languages, with two decimal separators. That is exactly the shape of thing
# that drifts silently and then gets discovered by a customer quoting the old
# number back at you — so the numbers live in the plan, and this checks that
# every file agrees with them.

LIST_PRICE = "11.90"
LAUNCH_PRICE = "8.90"
PRICED_FILES = [("README.md",),
                ("docs", "launch", "lyrion-forum-post.md"),
                ("docs", "launch", "reddit-r-squeezebox.md")]


def _prices_in(text):
    """Every euro amount, with the decimal comma normalised to a point."""
    return set(re.findall(r"(\d+[.,]\d{2})\s*€", text.replace(",", ".")))


@pytest.mark.parametrize("parts", PRICED_FILES,
                         ids=[p[-1] for p in PRICED_FILES])
def test_every_price_quoted_is_a_price_we_actually_charge(parts):
    quoted = _prices_in(_read(*parts))
    assert quoted, f"{parts[-1]} quotes no price at all"
    assert quoted <= {LIST_PRICE, LAUNCH_PRICE}, (
        f"{parts[-1]} quotes {sorted(quoted - {LIST_PRICE, LAUNCH_PRICE})}, "
        f"which is not the list price ({LIST_PRICE}) or the launch price "
        f"({LAUNCH_PRICE})")


def test_the_launch_posts_link_the_repository():
    # These were TODO placeholders long enough to be worth a check.
    for parts in PRICED_FILES[1:]:
        assert "github.com/LucaBon/vivavoce" in _read(*parts)


def test_the_launch_posts_promise_the_trial_and_the_refund():
    # Both are the offer, not decoration: the window is what makes the mic
    # felt before it is sold, and the refund is what makes the price a small
    # decision. A post that forgets either is selling something else.
    for parts in PRICED_FILES[1:]:
        text = _read(*parts).lower()
        assert "14 days of full pro" in text, f"{parts[-1]} drops the trial"
        assert "no questions asked" in text, f"{parts[-1]} drops the refund"


# -- the engine's front door ---------------------------------------------------
#
# engine/actions.py was 1054 lines and is now seven modules, with actions.py
# re-exporting the other six. That re-export is load-bearing: the router, the
# tools and a great many tests reach for actions.play_local, actions._score,
# actions.Guard — private names included — and the split promised none of them
# would notice. The promise is only kept while every name over there is still
# reachable from here, and forgetting one is silent until something breaks at
# runtime. So it is checked, the same way this module checks everything else
# the test suite cannot see.

ENGINE_PARTS = ("matching", "guard", "transport", "candidates", "library",
                "playback")


def _module_level_names(path):
    """Every function, class and constant a module defines at the top level."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def test_actions_re_exports_the_whole_engine():
    import actions

    missing = {}
    for part in ENGINE_PARTS:
        path = os.path.join(ROOT, "engine", f"{part}.py")
        absent = sorted(n for n in _module_level_names(path)
                        if not hasattr(actions, n))
        if absent:
            missing[part] = absent
    assert missing == {}, (
        f"engine/actions.py no longer re-exports {missing} — add them to the "
        f"import block at the bottom, or every caller that reaches through "
        f"actions breaks without warning")


# -- the Home Assistant blueprint ----------------------------------------------
#
# `blueprints/vivavoce_assist.yaml` is the one file in this repo that runs
# inside somebody else's program. Nothing else here can see it: it is not
# imported, not served, not copied into the image, and its mistakes surface as
# a voice assistant answering "Done" in a kitchen. These are the checks that a
# reading of the file would otherwise have to catch every time.

BLUEPRINT = ("blueprints", "vivavoce_assist.yaml")
# The route with the compatibility promise (docs/api.md). The unversioned
# /command alias exists and works, but a client that ships separately — which
# is exactly what a blueprint is — has no business calling the path that
# carries no version.
VERSIONED_ROUTE = "/api/v1/command"


class _Input(str):
    """Marker for a `!input name` node, carrying the input's name."""


def _load_blueprint():
    """The blueprint, with `!input` nodes preserved as _Input markers.

    ``yaml.safe_load`` cannot read this file — `!input` is Home Assistant's own
    tag — so the loader has to be taught it, and teaching it is also what makes
    the input cross-check below possible.
    """
    yaml = pytest.importorskip("yaml")

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!input",
                           lambda loader, node: _Input(node.value))
    return yaml.load(_read(*BLUEPRINT), Loader=Loader)


def _walk(node):
    """Every value in a nested dict/list, the containers included."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _deploy_rest_command():
    """The `rest_command:` YAML block DEPLOY.md tells people to paste."""
    yaml = pytest.importorskip("yaml")
    blocks = re.findall(r"```yaml\n(.*?)```", _read("DEPLOY.md"), re.S)
    for block in blocks:
        if block.lstrip().startswith("rest_command:"):
            return yaml.safe_load(block)["rest_command"]
    pytest.fail("DEPLOY.md no longer shows a rest_command block to paste")


def test_the_blueprint_is_a_blueprint():
    doc = _load_blueprint()
    meta = doc["blueprint"]
    assert meta["domain"] == "automation"
    assert meta["name"] and meta["description"]
    # Import-by-URL is the install route DEPLOY.md gives first, and Home
    # Assistant refuses to import a blueprint that does not name its source.
    assert meta["source_url"].endswith("/".join(BLUEPRINT))


def test_every_blueprint_input_is_declared_and_used():
    # Both directions, because they fail differently and both fail quietly.
    # An undeclared `!input` makes Home Assistant reject the whole blueprint at
    # import; a declared input nobody reads is a setting the user fills in and
    # that changes nothing — the worse of the two, because it looks like it
    # worked.
    doc = _load_blueprint()
    declared = set(doc["blueprint"]["input"])
    used = {str(n) for n in _walk(doc) if isinstance(n, _Input)}
    assert used - declared == set(), "!input names nothing declares"
    assert declared - used == set(), "declared inputs nothing reads"


def test_the_rest_command_calls_the_versioned_route():
    # DEPLOY.md carries the URL (rest_command lives in configuration.yaml, not
    # in a blueprint), so this is where the route is chosen.
    url = _deploy_rest_command()["vivavoce_command"]["url"]
    assert url.endswith(VERSIONED_ROUTE), (
        f"the blueprint's rest_command should call {VERSIONED_ROUTE}, the route "
        f"docs/api.md promises to keep, not {url}")


def test_the_blueprint_and_the_docs_agree_on_the_rest_command():
    # Two files, written at different times, in different languages: the name
    # in DEPLOY.md's snippet and the action the blueprint calls. Rename one and
    # the automation fails at the only moment nobody is watching — the first
    # time somebody speaks to it.
    documented = set(_deploy_rest_command())
    called = {str(step["action"]).split(".", 1)[1]
              for step in _walk(_load_blueprint())
              if isinstance(step, dict)
              and str(step.get("action", "")).startswith("rest_command.")}
    assert called and called <= documented, (
        f"the blueprint calls rest_command.{called} but DEPLOY.md defines "
        f"{documented}")


def test_the_rest_command_and_the_blueprint_pass_the_same_fields():
    # The other half of the same pair, and both directions matter because they
    # fail differently:
    #   sent but never read -> the field is dropped and the server answers as
    #     though it was never asked. Silent.
    #   read but never sent -> the template renders against an undefined
    #     variable, rest_command raises, `continue_on_error` turns that into
    #     "I cannot reach Vivavoce" — for a server that is up and correctly
    #     configured. Silent, permanent, and impossible to diagnose from the
    #     symptom.
    # Matching on the rendered variable names, not on substrings of the
    # template: `"player"` also occurs there as a JSON *key*, so a payload that
    # hardcoded it and never read the variable used to pass.
    command = _deploy_rest_command()["vivavoce_command"]
    read = set(re.findall(r"\{\{[-\s]*(\w+)", command["url"] + command["payload"]))
    sent = set()
    for step in _walk(_load_blueprint()):
        if (isinstance(step, dict)
                and str(step.get("action", "")).startswith("rest_command.")):
            sent |= set(step.get("data", {}))
    assert sent - read == set(), "the blueprint sends fields the template drops"
    assert read - sent == set(), (
        "DEPLOY.md's template reads variables the blueprint never sends: every "
        "call would raise on an undefined variable")


def test_the_blueprint_defaults_to_the_url_the_app_actually_serves():
    yaml = pytest.importorskip("yaml")
    options = yaml.safe_load(_read("ha-addon", "config.yaml"))["options"]
    default = _load_blueprint()["blueprint"]["input"]["server"]["default"]
    scheme = "https" if options["https"] else "http"
    assert default == f"{scheme}://localhost:{options['port']}", (
        f"the blueprint offers {default} but the Home Assistant app serves "
        f"{scheme} on {options['port']} — the default is the one setting most "
        f"people will never change")


def test_every_call_out_of_the_blueprint_can_fail_without_ending_the_script():
    # Found by running it: without `continue_on_error` a rest_command that
    # cannot connect aborts the script *before* set_conversation_response, and
    # Home Assistant answers with its own default — "Done". A confident "Done"
    # for a song that never started is the one failure this product does not
    # allow, and it needs no code of ours to happen.
    #
    # Every call out, not just the HTTP ones: assist_satellite.ask_question
    # raises too, when nobody answers.
    naked = [str(step["action"]) for step in _walk(_load_blueprint())
             if isinstance(step, dict) and "action" in step
             and step.get("continue_on_error") is not True]
    assert naked == [], (
        f"{naked} can raise and end the turn as Assist's own 'Done'; mark them "
        f"`continue_on_error: true` and answer for ourselves")


def test_every_branch_of_the_blueprint_ends_by_answering():
    # The property the test above only approximates. `continue_on_error` keeps
    # one action from aborting the script; this checks the thing that actually
    # matters, which is that no route through the actions can reach the end
    # without having said something. A branch that falls off the end is
    # answered by Assist, not by us, and Assist says "Done".
    def answers(sequence):
        """Does every path through this action list set a response?"""
        for step in sequence:
            if not isinstance(step, dict):
                continue
            if "set_conversation_response" in step:
                return True
            if "choose" in step:
                # Every option, and the default — an absent default means
                # "fall through", which is exactly the hole being looked for.
                options = [opt.get("sequence", []) for opt in step["choose"]]
                if "default" not in step:
                    return False
                options.append(step["default"])
                if all(answers(opt) for opt in options):
                    return True
            if "if" in step:
                if ("else" in step
                        and answers(step.get("then", []))
                        and answers(step["else"])):
                    return True
        return False

    assert answers(_load_blueprint()["actions"]), (
        "a path through the blueprint reaches the end without calling "
        "set_conversation_response: on that path Home Assistant answers "
        "'Done' for us")


def test_the_blueprint_only_names_streaming_services_the_engine_has():
    # «da spotify metti X» would match the trigger, miss the `service` pattern
    # in localvoice/lang/, fall through to a plain play, and start the song on
    # TIDAL *without saying so*. Answering from a different source than the one
    # asked for, silently, is the exact failure this whole blueprint exists to
    # prevent — so the names are pinned to the ones the engine really has.
    import lms

    known = set(lms.SERVICES) | {"tidal", "qobuz"}
    named = set()
    for trigger in _load_blueprint()["triggers"]:
        for sentence in trigger["command"]:
            for group in re.findall(r"\(([^()]*)\)", sentence):
                named |= {w for w in group.split("|") if w in known or
                          w in {"spotify", "deezer", "apple music", "napster",
                                "amazon", "youtube", "plex"}}
    assert named <= known, (
        f"the blueprint offers {named - known}, which engine/lms.py has no "
        f"ServiceSpec for")


# -- what the documents promise, against what the code does --------------------
#
# Found in review, twice over, and both times the same shape: a capability the
# code had, that no page a stranger reads knew about. The add-on offered three
# `library*` options that run.sh and entrypoint.sh both carry (the tests above
# prove the plumbing end to end) and that DOCS.md never named; docs/api.md —
# the one document an outside client author reads — listed four languages when
# engine/catalogs/ has had five since Spanish landed. Neither is the kind of
# drift a person catches by re-reading, so neither is left to a person.

def test_every_addon_option_is_documented():
    yaml = pytest.importorskip("yaml")
    schema = yaml.safe_load(_read("ha-addon", "config.yaml"))["schema"]
    docs = _read("ha-addon", "DOCS.md")
    # The options table spells each key in backticks in the first column.
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", docs, re.M))
    missing = set(schema) - documented
    assert not missing, (
        f"ha-addon/config.yaml offers {sorted(missing)}, which the page the "
        f"add-on's users read never mentions — document it in DOCS.md's "
        f"options table or drop it from the schema")


def test_the_api_contract_names_every_language_the_engine_answers_in():
    sys.path.insert(0, os.path.join(ROOT, "engine"))
    from messages import CATALOGS

    row = [line for line in _read("docs", "api.md").splitlines()
           if line.startswith("| `lang` |")]
    assert len(row) == 1, "docs/api.md has no single `lang` row to check"
    named = set(re.findall(r"`([a-z]{2})`", row[0]))
    missing = set(CATALOGS) - named
    assert not missing, (
        f"engine/catalogs/ answers in {sorted(missing)} and docs/api.md does "
        f"not say so — a client author reads that row, not the README")


def test_every_ci_job_has_a_timeout():
    # Found in review: not one job in either workflow declared a tetto, so a
    # deadlock — the plausible failure in code that runs semaphores, an RLock
    # and a thread pool — would have burned GitHub's 360-minute default before
    # failing. On a matrix this wide that is an afternoon of runners for
    # something visible in twenty minutes. The numbers come from real run
    # durations (pytest 213s, e2e 138s, docker 56s) with room for a cold cache.
    yaml = pytest.importorskip("yaml")
    for name in ("ci.yml", "release.yml"):
        jobs = yaml.safe_load(_read(".github", "workflows", name))["jobs"]
        for job, spec in jobs.items():
            assert "timeout-minutes" in spec, (
                f"{name}: job '{job}' has no timeout-minutes, so a hang costs "
                f"GitHub's 360-minute default")
            assert spec["timeout-minutes"] <= 30, (
                f"{name}: job '{job}' allows {spec['timeout-minutes']} minutes; "
                f"nothing here legitimately takes that long")


# -- a pipe into a reader that stops early ------------------------------------
#
# Every step here runs under `pipefail` (GitHub's bash default, and `set -euo
# pipefail` besides). Under it `producer | grep -q x` fails whenever grep finds
# `x` and exits while the producer is still writing: the producer dies of
# SIGPIPE, the pipeline returns 141, and the step goes red having found exactly
# what it was looking for. It depends on how much output follows the match, so
# it passes for weeks and then fails a release — the add-on start-up check did,
# on `docker logs addon | grep -q "Pronto"`, the day 0.8.0 was tagged.
# `grep -m` and `head` stop early the same way. Read the output first, then
# search it: `grep -q x <<<"$(producer)"`.

#: A single `|` (not `||`, which is "or") into `grep -q`/`-m` or `head`.
EARLY_EXIT_READER = re.compile(
    r"(?<!\|)\|(?!\|)\s*(?:grep\s+(?:-\w*[qm]\w*\b)|head\b)")


def _run_scripts(path):
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(_read(*path))
    steps = []
    for job in (doc.get("jobs") or {}).values():
        steps += job.get("steps") or []
    steps += (doc.get("runs") or {}).get("steps") or []
    return [str(step.get("run", "")) for step in steps]


@pytest.mark.parametrize("path", [
    (".github", "workflows", "ci.yml"),
    (".github", "workflows", "release.yml"),
    ADDON_ACTION,
], ids=lambda p: p[-1])
def test_no_step_pipes_into_a_reader_that_stops_early(path):
    offending = [line.strip() for script in _run_scripts(path)
                 for line in script.splitlines()
                 if not line.strip().startswith("#")
                 and EARLY_EXIT_READER.search(line)]
    assert offending == [], (
        "under pipefail these fail with 141 when the reader exits first — "
        f"read the output, then search it: {offending}")
