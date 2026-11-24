#!/usr/bin/env bash
# Generate code for the e2e fixture with buf + the local protoc-gen-fory.
#
#   scripts/ci/generate.sh <lang> [<lang> ...]
#
# Writes tests/e2e/out/<lang>/. Needs buf on PATH.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
for lang in "$@"; do
  uv run python tests/e2e/generate.py "$lang"
done
