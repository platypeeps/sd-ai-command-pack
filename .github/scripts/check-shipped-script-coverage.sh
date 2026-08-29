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

run_coverage_report --include="templates/scripts/sd-ai-command-pack-*.py,templates/scripts/sd_ai_command_pack_lib.py,templates/scripts/sd_ai_command_pack_fleet_lib.py" --fail-under=76

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
templates/scripts/sd-ai-command-pack-audit-route.py 77
templates/scripts/sd-ai-command-pack-audit-inventory.py 85
templates/scripts/sd-ai-command-pack-check.py 74
templates/scripts/sd-ai-command-pack-fleet-controller.py 76
templates/scripts/sd-ai-command-pack-fleet-finding-classify.py 85
templates/scripts/sd-ai-command-pack-thin-resweep.py 76
templates/scripts/sd-ai-command-pack-fleet-timing.py 88
templates/scripts/sd-ai-command-pack-fleet-wave-plan.py 85
templates/scripts/sd-ai-command-pack-housekeeping-result.py 97
templates/scripts/sd-ai-command-pack-install-audit.py 89
templates/scripts/sd-ai-command-pack-pr-body-scope.py 78
templates/scripts/sd-ai-command-pack-pr-eligibility.py 85
templates/scripts/sd-ai-command-pack-record-session.py 79
templates/scripts/sd-ai-command-pack-recovery-artifacts.py 80
templates/scripts/sd-ai-command-pack-review-layout.py 95
templates/scripts/sd-ai-command-pack-review-learnings.py 79
templates/scripts/sd-ai-command-pack-review-local.py 70
templates/scripts/sd-ai-command-pack-review.py 70
templates/scripts/sd-ai-command-pack-status.py 80
templates/scripts/sd-ai-command-pack-surface-check.py 70
templates/scripts/sd-ai-command-pack-update-spec-kb.py 83
templates/scripts/sd-ai-command-pack-work-loop.py 80
templates/scripts/sd_ai_command_pack_lib.py 88
templates/scripts/sd_ai_command_pack_fleet_lib.py 90
EOF
