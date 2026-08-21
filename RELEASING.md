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

### 1. Bump the version in both files

They are hand-edited copies of one number:

- `pyproject.toml` → `version = "X.Y.Z"`
- `ha-addon/config.yaml` → `version: "X.Y.Z"`

`tests/test_packaging.py::test_addon_version_matches_pyproject` fails if they
disagree, so you cannot forget the second one.

The HA Supervisor compares its copy against what is installed to decide whether
an update exists — a stale add-on version means users are never offered the
update.

### 2. Write the CHANGELOG entry

Add `## X.Y.Z — <Month Year>` at the top of `CHANGELOG.md`, dated when it
actually reaches `main` (not when the work started).
`test_changelog_documents_the_current_version` checks the heading exists.

Sections in use: `### New`, `### Removed`, `### Internal` (CI, tests, build —
anything that does not change what a user sees).

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

### 5. Check CI and the add-on build

CI runs on the push to `main`: the suite on Python 3.9–3.14 plus Windows,
`compileall`, and the root Docker image.

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

- **Docker Hub / compose users** track the image, not the tag; the HA add-on is
  the only consumer pinned to tags.
- **The add-on slug** changed at 0.2.0 (`squeezesay` → `vivavoce`), so the
  Supervisor treats it as a new add-on for anyone from before then: they
  reinstall rather than update, and version comparison never enters into it.
- **Version numbers** are pre-1.0: features → minor bump, build/CI/docs-only →
  patch bump, or fold them into the next real release rather than shipping a
  version whose only content is plumbing.
