"""Fail if a version is already released.

    python -I scripts/ci/release_check.py <version>

Env: GITHUB_REPOSITORY (owner/repo), GITHUB_TOKEN (optional, avoids rate limits),
PYPI_PROJECT (default: protoc-gen-fory).

A version counts as released once its tag ``v<version>`` exists on GitHub: the
tag is created last, together with the GitHub release. A version that is on
PyPI without a tag is the leftover of a release run that failed after the
upload. That is only a warning: the rerun skips the existing files
(``uv publish --check-url``) and finishes the release.

Writes ``prerelease=true|false`` to $GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

Fetch = Callable[[str, dict[str, str]], int]

_PRERELEASE = re.compile(r"(a|b|rc|\.dev)\d+")


def http_status(url: str, headers: dict[str, str]) -> int:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def is_prerelease(version: str) -> bool:
    return bool(_PRERELEASE.search(version))


def check(
    version: str, repo: str, pypi_project: str, token: str | None, fetch: Fetch = http_status
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    if "+" in version:
        return [f"{version} is a local version; only plain versions are released"], []
    errors: list[str] = []
    warnings: list[str] = []
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    tag = f"v{version}"
    status = fetch(f"https://api.github.com/repos/{repo}/git/ref/tags/{tag}", headers)
    if status == 200:
        errors.append(
            f"release {tag} already exists in {repo}. Bump the version in pyproject.toml "
            "and add a CHANGELOG.md section for it"
        )
    elif status != 404:
        errors.append(f"could not check tag {tag} on GitHub (HTTP {status})")

    status = fetch(f"https://pypi.org/pypi/{pypi_project}/{version}/json", {})
    if status == 200 and not errors:
        warnings.append(
            f"{pypi_project} {version} is already on PyPI but {tag} does not exist: "
            "finishing an interrupted release (existing files are skipped)"
        )
    elif status not in (200, 404):
        errors.append(f"could not check PyPI for {pypi_project} {version} (HTTP {status})")
    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    version = argv[0]
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("::error::GITHUB_REPOSITORY is not set", file=sys.stderr)
        return 2
    errors, warnings = check(
        version,
        repo,
        os.environ.get("PYPI_PROJECT", "protoc-gen-fory"),
        os.environ.get("GITHUB_TOKEN"),
    )
    for warning in warnings:
        print(f"::warning::{warning}")
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    prerelease = is_prerelease(version)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"prerelease={json.dumps(prerelease)}\n")
    print(f"v{version} is not released yet (prerelease: {prerelease})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
