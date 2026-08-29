# Licensing overview

Vivavoce is **open-core**:

- **Core — AGPL-3.0.** Everything in this repository except `localvoice/pro/`
  is free software under the GNU Affero General Public License v3
  ([LICENSE](../LICENSE)): the engine, the router, the web server, and the
  text and transport features. Free forever.
- **Pro — proprietary.** The files under `localvoice/pro/` (and the features
  marked "Pro" in the README) are licensed under the
  [Vivavoce Pro EULA](PRO-EULA.md) and unlocked by a one-time purchase of a
  license key.

Why: the paid Pro tier funds the development of everything else. The code is
visible and the license check is trust-based by design — no DRM, no
obfuscation. If you find the tool useful, the key is how you keep it alive.

## Third-party software

Vivavoce ships **no third-party code**: the core is stdlib-only, and the
optional extras (`cryptography`, `faster-whisper`) are installed by the user,
not vendored here.

One project deserves naming anyway, because the app puts its interface on
screen:

- **[Material Skin](https://github.com/CDrummond/lms-material)** — MIT,
  © 2017 Craig Drummond. The "browse" panel frames the Material Skin **already
  installed on your own LMS**, served through this app's reverse proxy
  (`localvoice/lmsproxy.py`) so an HTTPS page can show a plain-HTTP one. Not a
  line of it is copied, bundled or redistributed by this repository, and
  nothing about how it works is changed. If you use it, consider
  [supporting its author](https://github.com/CDrummond/lms-material#donations).
