#!/usr/bin/env python3
"""The CI matrix for the Home Assistant add-on image, derived from the add-on.

Both workflows build that image, and before this script both carried their own
hand-written list of the three architectures. RELEASING.md is largely the story
of what happens when one fact lives in several hand-edited places, so this is
the one place it lives: ``ha-addon/config.yaml`` says which architectures the
add-on claims, ``ha-addon/build.yaml`` says what each one builds from, and
adding a fourth means editing those two files and nothing else.

    python3 tools/ci_addon_matrix.py

prints the JSON a workflow feeds to ``strategy.matrix.include``, one object per
architecture with the Docker platform to build for and the machine name that
architecture reports — the job compares ``uname -m`` against the latter, so an
ARM leg that quietly ran on x86 fails instead of going green.

**Standard library only, and it parses the two files by hand.** Not an
aesthetic choice: this runs on a bare runner in a job that installs neither uv
nor PyYAML, and adding a dependency install to buy `yaml.safe_load` would cost
more than the twenty lines below. The narrow parser is held to the real thing
by tests/test_packaging.py, which loads the same files with PyYAML and demands
the same answer — so the day one of them grows a shape this cannot read, a
test says so rather than a workflow silently building fewer architectures.
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every architecture Home Assistant has built add-ons for, not only the two
# this one still claims: the point is that adding an arch to config.yaml needs
# no edit here. The three 32-bit names are kept for that reason and not
# because they are usable — Home Assistant stopped publishing those bases with
# 2025.12. The second element is what `uname -m` reports on that platform,
# which is not always guessable from the name — HA's "armhf" is armv6, and
# amd64 calls itself x86_64.
PLATFORMS = {
    "amd64": ("linux/amd64", "x86_64"),
    "i386": ("linux/386", "i686"),
    "aarch64": ("linux/arm64", "aarch64"),
    "armv7": ("linux/arm/v7", "armv7l"),
    "armhf": ("linux/arm/v6", "armv6l"),
}


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _block(text: str, key: str):
    """The indented lines under a top-level ``key:``, comments and blanks gone."""
    lines = []
    inside = False
    for line in text.splitlines():
        if re.match(rf"^{re.escape(key)}:\s*$", line):
            inside = True
            continue
        if not inside:
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():  # a new top-level key ends the block
            break
        lines.append(line)
    return lines


def declared_arches():
    """The architectures ``config.yaml`` advertises, in the order it lists them."""
    arches = []
    for line in _block(_read("ha-addon", "config.yaml"), "arch"):
        match = re.match(r"^\s+-\s+(\S+)\s*$", line)
        if match:
            arches.append(match.group(1))
    return arches


def base_images():
    """``build.yaml``'s architecture to base-image map."""
    bases = {}
    for line in _block(_read("ha-addon", "build.yaml"), "build_from"):
        match = re.match(r"^\s+([A-Za-z0-9_]+):\s*(\S+)\s*$", line)
        if match:
            bases[match.group(1)] = match.group(2)
    return bases


def matrix():
    bases = base_images()
    legs = []
    for arch in declared_arches():
        if arch not in PLATFORMS:
            raise SystemExit(
                f"{arch}: config.yaml declares an architecture this script has "
                f"no Docker platform for — add it to PLATFORMS above")
        if arch not in bases:
            raise SystemExit(
                f"{arch}: config.yaml declares it but ha-addon/build.yaml has "
                f"no build_from entry, so nothing knows what to build it from")
        platform, machine = PLATFORMS[arch]
        legs.append({"arch": arch, "platform": platform,
                     "machine": machine, "base": bases[arch]})
    if not legs:
        raise SystemExit("ha-addon/config.yaml declares no architectures at all")
    return legs


def main() -> int:
    # One line, because a workflow reads this through $GITHUB_OUTPUT.
    print(json.dumps(matrix(), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
