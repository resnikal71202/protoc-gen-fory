"""Check CHANGELOG.md against a version and extract release notes.

    python -I scripts/ci/changelog.py check <version>     # section exists
    python -I scripts/ci/changelog.py release <version>   # section exists and is dated
    python -I scripts/ci/changelog.py notes <version>     # print the section body

Sections look like ``## [0.1.0] - 2026-12-01`` (or ``- Unreleased``).
Local version labels (``0.1.0+branch.7``) are checked against their public part.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
_HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?:\s+-\s+(?P<date>.+?))?\s*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ChangelogError(Exception):
    pass


def sections(text: str) -> dict[str, tuple[str | None, str]]:
    """version -> (date or None, body)."""
    result: dict[str, tuple[str | None, str]] = {}
    current: str | None = None
    date: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match or (line.startswith("[") and "]: " in line and current):
            if current is not None:
                result[current] = (date, "\n".join(body).strip())
            current, body = None, []
        if match:
            current = match.group("version")
            date = match.group("date")
            continue
        if current is not None:
            body.append(line)
    if current is not None:
        result[current] = (date, "\n".join(body).strip())
    return result


def section(text: str, version: str, *, require_date: bool) -> str:
    public = version.split("+", 1)[0]
    found = sections(text)
    if public not in found:
        raise ChangelogError(f"CHANGELOG.md has no section '## [{public}]'")
    date, body = found[public]
    if not body:
        raise ChangelogError(f"CHANGELOG.md section [{public}] is empty")
    if require_date and not (date and _DATE.match(date)):
        raise ChangelogError(
            f"CHANGELOG.md section [{public}] needs a release date "
            f"('## [{public}] - YYYY-MM-DD'), found {date or 'none'!r}"
        )
    return body


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("check", "release", "notes"):
        print(__doc__, file=sys.stderr)
        return 2
    command, version = argv
    try:
        body = section(CHANGELOG.read_text(), version, require_date=command == "release")
    except ChangelogError as exc:
        print(f"::error file=CHANGELOG.md::{exc}")
        return 1
    if command == "notes":
        print(body)
    else:
        print(f"CHANGELOG.md has a section for {version.split('+', 1)[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
