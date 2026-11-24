#!/usr/bin/env bash
# Roundtrip test (WP6): serialize in <writer>, deserialize in <reader>.
#
#   scripts/ci/roundtrip.sh <writer> <reader>
#
# Generates code for both languages, then runs the roundtrip tests in
# tests/e2e (marker `roundtrip`), which read the pair from
# FORY_RT_WRITER / FORY_RT_READER.
set -euo pipefail

writer="${1:?usage: roundtrip.sh <writer> <reader>}"
reader="${2:?usage: roundtrip.sh <writer> <reader>}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ "$writer" == "$reader" ]]; then
  "$root/scripts/ci/generate.sh" "$writer"
else
  "$root/scripts/ci/generate.sh" "$writer" "$reader"
fi

cd "$root"
FORY_RT_WRITER="$writer" FORY_RT_READER="$reader" \
  uv run --group e2e pytest tests/e2e -m roundtrip -v
