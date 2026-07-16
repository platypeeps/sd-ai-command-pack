#!/usr/bin/env bash
# Enforce aggregate and per-file coverage floors for shipped Python helpers.
set -euo pipefail

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

run_coverage_report() {
  "$PYTHON_BIN" -m coverage report "$@"
}

run_coverage_report --include="scripts/sd-ai-command-pack-*.py" --fail-under=76

while read -r script floor; do
  case "$script" in
    "" | \#*) continue ;;
  esac
  if [ ! -f "$script" ]; then
    printf 'error: coverage floor references missing script: %s\n' "$script" >&2
    exit 1
  fi
  printf '\n==> %s coverage floor %s%%\n' "$script" "$floor"
  run_coverage_report --include="$script" --fail-under="$floor"
done <<'EOF'
scripts/sd-ai-command-pack-fleet-preflight.py 82
scripts/sd-ai-command-pack-install-audit.py 89
scripts/sd-ai-command-pack-pr-body-scope.py 78
scripts/sd-ai-command-pack-record-session.py 79
scripts/sd-ai-command-pack-review-learnings.py 73
scripts/sd-ai-command-pack-update-spec-kb.py 83
EOF
