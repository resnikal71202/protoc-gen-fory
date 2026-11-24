"""Generate code for the e2e fixture with buf + protoc-gen-fory.

    uv run python tests/e2e/generate.py <lang>

Writes tests/e2e/out/<lang>/ (git-ignored). Uses the same buf workspace setup
as the golden tests (fixture tests/fixtures/multi + fory/options.proto).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

E2E = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E.parent))

import helpers  # noqa: E402

FIXTURE = helpers.FIXTURES / "multi"


def main(lang: str) -> int:
    out = E2E / "out" / lang
    shutil.rmtree(out, ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        tree = helpers.run_buf(FIXTURE, lang, Path(tmp))
    if not tree:
        print(f"buf generate produced no files for {lang}", file=sys.stderr)
        return 1
    for name, content in tree.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(f"generated {len(tree)} file(s) in {out.relative_to(E2E.parent.parent)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in helpers.LANGUAGES:
        sys.exit(f"usage: generate.py <{'|'.join(helpers.LANGUAGES)}>")
    sys.exit(main(sys.argv[1]))
