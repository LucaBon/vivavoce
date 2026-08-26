# Releasing Vivavoce

Branching is git-flow: work lands on `develop` through a PR, and a release is
`develop` merged into `main` and tagged. `main` is the released line.

**The one rule that bites: the tag is not optional.** `ha-addon/Dockerfile`
downloads `refs/tags/v${BUILD_VERSION}.tar.gz`, where `BUILD_VERSION` is the
version in `ha-addon/config.yaml`. Bump the version without pushing the
matching tag and every Home Assistant add-on build fails with a 404. That is
deliberate — a loud failure at release time beats silently shipping unreleased
code — but it means **the version bump and the tag go out together**.

## Steps

### 1. Bump the version in both files, and the pins that quote it

They are hand-edited copies of one number:

- `pyproject.toml` → `version = "X.Y.Z"`
- `ha-addon/config.yaml` → `version: "X.Y.Z"`

`tests/test_packaging.py::test_addon_version_matches_pyproject` fails if they
disagree, so you cannot forget the second one.

The HA Supervisor compares its copy against what is installed to decide whether
an update exists — a stale app version means users are never offered the
update.

There is a **third** hand-edited copy, and until 2026-08-26 nothing watched it:
the image tag `DEPLOY.md` tells people to pin, written as a backticked
`:X.Y.Z` with a `:X.Y` beside it. It recommended the 0.3.0 tag for weeks
against a declared 0.2.0, which does not fail here — it fails at
`docker pull`, with a manifest-unknown error, on the machine of somebody
following the install guide to the letter.
`test_docs_quote_the_declared_version` now fails if a doc quotes a tag that is
not the declared version, so update `DEPLOY.md` in the same edit.

### 2. Write the CHANGELOG entries — both of them

Add `## X.Y.Z — <Month Year>` at the top of `CHANGELOG.md`, dated when it
actually reaches `main` (not when the work started).
`test_changelog_documents_the_current_version` checks the heading exists.

Sections in use: `### New`, `### Removed`, `### Internal` (CI, tests, build —
anything that does not change what a user sees).

Then `ha-addon/CHANGELOG.md`, which is the app's own and is **not** a copy of
the root one: rename its `## [Non rilasciato]` heading to
`## [X.Y.Z] - YYYY-MM-DD`. It is in Italian, like everything else in that
folder, and it deliberately leaves out what does not reach someone installing
the app — the published Docker image, the optional engines the app's image does
not ship. `test_the_addon_has_its_own_changelog` fails while the version has no
heading there.

### 3. Merge to `main`

```bash
git checkout develop && git pull
uv run pytest                       # green before anything leaves develop

git checkout main && git pull
git merge --no-ff develop -m "Merge branch 'develop' into main"
git push origin main
```

### 4. Tag it — same breath as the push

```bash
git tag -a vX.Y.Z -m "Vivavoce X.Y.Z" <the main merge commit>
git push origin vX.Y.Z
```

The tag must point at the **`main` merge commit**, so the tagged tree is
exactly what a release build downloads. Tag *after* the merge, never before.

### 5. Watch the release workflow publish the image

Pushing the tag starts `.github/workflows/release.yml`, which builds the image
for amd64 and arm64 and pushes it to GHCR as `:X.Y.Z`, `:X.Y` and `:latest`.
It refuses to publish if the tag disagrees with `pyproject.toml`, which is the
mistake this whole file exists to prevent — so a red release job usually means
step 1 was half-done, not that the build is broken.

Nothing else needs doing: the token is the workflow's own `GITHUB_TOKEN`.

### 6. Check CI and the add-on build

CI runs on the push to `main`: the suite on Python 3.9–3.14 plus Windows,
`compileall`, and the root Docker image. Note it does **not** run on the tag —
tags are the release workflow's business, which is why that workflow re-checks
the packaging invariants itself.

CI does **not** build the add-on image (it needs `BUILD_FROM` and the network),
so verify that by hand once the tag is pushed:

```bash
cd ha-addon
docker build \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.21 \
  --build-arg BUILD_VERSION=X.Y.Z \
  -t vivavoce-addon-check .
docker run --rm --entrypoint sh vivavoce-addon-check -c "ls /app"
docker rmi vivavoce-addon-check
```

Expect `deploy engine localvoice tools`. A 404 here means the tag is missing or
misnamed — the directory inside the tarball drops the leading `v`
(`v0.2.0` → `vivavoce-0.2.0/`), which the Dockerfile already accounts for.

## Notes

- **Image users** track `:latest` (or a pinned `:X.Y`), not the git tag — but
  the tag is what publishes the image, so it is no longer optional for them
  either. The HA add-on remains the consumer that resolves a tag by name.
- **The add-on slug** changed at 0.2.0 (`squeezesay` → `vivavoce`), so the
  Supervisor treats it as a new add-on for anyone from before then: they
  reinstall rather than update, and version comparison never enters into it.
- **Version numbers** are pre-1.0: features → minor bump, build/CI/docs-only →
  patch bump, or fold them into the next real release rather than shipping a
  version whose only content is plumbing.
