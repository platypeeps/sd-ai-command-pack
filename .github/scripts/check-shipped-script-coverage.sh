#!/usr/bin/env bash
# Enforce aggregate and per-file coverage floors for shipped Python helpers.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

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

run_coverage_report --include="scripts/sd-ai-command-pack-*.py,scripts/sd_ai_command_pack_lib.py,scripts/sd_ai_command_pack_fleet_lib.py" --fail-under=76

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
scripts/sd-ai-command-pack-audit-route.py 77
scripts/sd-ai-command-pack-fleet-preflight.py 82
scripts/sd-ai-command-pack-fleet-candidate-check.py 90
scripts/sd-ai-command-pack-fleet-controller.py 76
scripts/sd-ai-command-pack-fleet-finding-classify.py 85
scripts/sd-ai-command-pack-fleet-review-classify.py 80
scripts/sd-ai-command-pack-fleet-timing.py 88
scripts/sd-ai-command-pack-fleet-wave-plan.py 85
scripts/sd-ai-command-pack-housekeeping-result.py 97
scripts/sd-ai-command-pack-install-audit.py 89
scripts/sd-ai-command-pack-pr-body-scope.py 78
scripts/sd-ai-command-pack-pr-eligibility.py 85
scripts/sd-ai-command-pack-record-session.py 79
scripts/sd-ai-command-pack-review-learnings.py 79
scripts/sd-ai-command-pack-status.py 80
scripts/sd-ai-command-pack-update-spec-kb.py 83
scripts/sd-ai-command-pack-work-loop.py 80
scripts/sd_ai_command_pack_lib.py 88
scripts/sd_ai_command_pack_fleet_lib.py 90
EOF
