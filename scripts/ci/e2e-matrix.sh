#!/usr/bin/env bash
# Print the e2e job matrices as GitHub Actions outputs (key=JSON).
#
#   scripts/ci/e2e-matrix.sh [pr|full]
#
# langs:  languages that have an e2e project in tests/e2e/<lang>/
# pairs:  roundtrip (writer, reader) pairs
#         pr:   each language against Java in both directions (+ java->java);
#               self-roundtrip only, while there is no Java project yet
#         full: every writer x reader combination
set -euo pipefail

mode="${1:-pr}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

langs=()
for lang in rust java go python javascript; do
  [[ -d "$root/tests/e2e/$lang" ]] && langs+=("$lang")
done

has_java=false
for lang in "${langs[@]}"; do [[ "$lang" == java ]] && has_java=true; done

pairs=()
for w in "${langs[@]}"; do
  for r in "${langs[@]}"; do
    case "$mode" in
      full) pairs+=("$w:$r") ;;
      pr)
        if $has_java; then
          [[ "$w" == java || "$r" == java ]] && pairs+=("$w:$r")
        else
          [[ "$w" == "$r" ]] && pairs+=("$w:$r")
        fi
        ;;
      *) echo "unknown mode: $mode" >&2; exit 2 ;;
    esac
  done
done

json_langs="["
for i in "${!langs[@]}"; do
  [[ $i -gt 0 ]] && json_langs+=","
  json_langs+="\"${langs[$i]}\""
done
json_langs+="]"

json_pairs="["
for i in "${!pairs[@]}"; do
  [[ $i -gt 0 ]] && json_pairs+=","
  json_pairs+="{\"writer\":\"${pairs[$i]%%:*}\",\"reader\":\"${pairs[$i]##*:}\"}"
done
json_pairs+="]"

echo "langs=$json_langs"
echo "pairs=$json_pairs"
