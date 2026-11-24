#!/usr/bin/env bash
# Compile test (WP6): generate Fory code for one language with buf + protoc-gen-fory
# and check it with that language's toolchain against the Fory runtime.
#
#   scripts/ci/compile.sh <rust|java|go|python|javascript>
#
# Each language has a small project in tests/e2e/<lang>/ (see .github/CI.md).
set -euo pipefail

lang="${1:?usage: compile.sh <lang>}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
e2e="$root/tests/e2e"

if [[ ! -d "$e2e/$lang" ]]; then
  echo "no e2e project for $lang in tests/e2e/$lang" >&2
  exit 2
fi
"$root/scripts/ci/generate.sh" "$lang"

case "$lang" in
  python)
    # Import every generated module with the pinned pyfory runtime.
    # (mypy is not part of the check: foryc's oneof classes assign attributes
    # outside __slots__, which mypy rejects. That is upstream generator output.)
    cd "$root"
    uv run --group e2e pytest "tests/e2e/python" -k "import" -v
    ;;
  rust)
    cargo check --locked --manifest-path "$e2e/rust/Cargo.toml"
    ;;
  java)
    cd "$e2e/java"
    if [[ -x ./gradlew ]]; then ./gradlew build --no-daemon; else gradle build --no-daemon; fi
    ;;
  go)
    cd "$e2e/go"
    go build ./...
    go vet ./...
    ;;
  javascript)
    cd "$e2e/javascript"
    npm ci
    npx tsc --noEmit
    ;;
  *)
    echo "unknown language: $lang" >&2
    exit 2
    ;;
esac
