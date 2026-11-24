"""Compute the package version for a CI build.

    python -I scripts/ci/build_version.py <base version> <branch> <build number>

* On ``main``: the base version from pyproject.toml, unchanged.
* On any other branch: ``<base>+<branch>.<build number>``, a PEP 440 local
  version. The branch name is lowercased and every run of characters other
  than letters and digits becomes a dot (``feature/Foo_bar`` ->
  ``feature.foo.bar``). PEP 440 normalizes ``-`` in local labels to ``.``,
  so ``0.1.0+feature-foo-42`` and ``0.1.0+feature.foo.42`` are the same version.

Local versions cannot be uploaded to PyPI, so branch builds never reach it.
"""

from __future__ import annotations

import re
import sys

MAIN = "main"


def local_label(branch: str) -> str:
    label = re.sub(r"[^a-z0-9]+", ".", branch.lower()).strip(".")
    if not label:
        raise ValueError(f"branch name {branch!r} has no letters or digits")
    return label


def build_version(base: str, branch: str, build_number: str) -> str:
    if "+" in base:
        raise ValueError(f"base version {base!r} already has a local label")
    if not build_number.isdigit():
        raise ValueError(f"build number must be digits, got {build_number!r}")
    if branch == MAIN:
        return base
    return f"{base}+{local_label(branch)}.{build_number}"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(build_version(*argv))
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
