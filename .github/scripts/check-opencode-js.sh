#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if ! command -v node >/dev/null 2>&1; then
  printf '%s\n' "error: node is required to syntax-check tracked OpenCode JavaScript" >&2
  exit 127
fi

files=()
while IFS= read -r -d '' path; do
  case "$path" in
    .opencode/*.js|templates/.opencode/*.js)
      files+=("$path")
      ;;
  esac
done < <(git ls-files -z -- '*.js')

if [ "${#files[@]}" -eq 0 ]; then
  printf '%s\n' "No tracked OpenCode JavaScript files found."
  exit 0
fi

for file in "${files[@]}"; do
  node --check "$file"
done
