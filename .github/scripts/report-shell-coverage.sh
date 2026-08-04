#!/usr/bin/env bash
# Merge the per-invocation kcov runs produced by kcov-bash-shim.sh during the
# test suite, publish the measured shipped-shell line coverage, and fail loudly
# on a zero measurement. Publishing a number changes no gate (no floor yet, per
# the measure-before-gating rule); the hard failure guards only against silent
# zero-line plumbing breakage.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

kcov_dir="${SD_AI_COMMAND_PACK_KCOV_DIR:?SD_AI_COMMAND_PACK_KCOV_DIR must be set}"
merged_dir="${SD_AI_COMMAND_PACK_KCOV_MERGED:-$kcov_dir/merged}"

shopt -s nullglob
runs=("$kcov_dir"/run-*)
shopt -u nullglob
if [ "${#runs[@]}" -eq 0 ]; then
  printf 'error: no kcov run directories under %s; the coverage shim never executed.\n' \
    "$kcov_dir" >&2
  exit 1
fi

printf 'diagnostic: %s kcov run director(ies) under %s\n' "${#runs[@]}" "$kcov_dir" >&2

kcov --merge "$merged_dir" "${runs[@]}"

printf 'diagnostic: cobertura.xml files under %s:\n' "$merged_dir" >&2
find "$merged_dir" -name 'cobertura.xml' >&2 || true

# Prefer the merged report; fall back to any cobertura kcov emitted.
cobertura="$merged_dir/kcov-merged/cobertura.xml"
if [ ! -f "$cobertura" ]; then
  cobertura="$(find "$merged_dir" -name 'cobertura.xml' -print -quit)"
fi
if [ -z "$cobertura" ] || [ ! -f "$cobertura" ]; then
  printf 'error: kcov produced no cobertura.xml under %s\n' "$merged_dir" >&2
  exit 1
fi
printf 'diagnostic: using cobertura %s\n' "$cobertura" >&2

# summarize_shell_coverage.py exits non-zero on a zero/unreadable measurement
# (printing the reason to stderr) and prints "<covered> <total> <pct>" on
# success. Capture it in a command substitution so its exit status propagates —
# a process substitution would swallow it and defeat the zero-line guard.
if ! summary="$(python3 .github/scripts/summarize_shell_coverage.py "$cobertura")"; then
  exit 1
fi
read -r covered total pct <<<"$summary"

printf 'shipped shell coverage: %s%% (%s/%s lines)\n' "$pct" "$covered" "$total"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    printf '%s\n' "## Shipped shell coverage"
    printf '%s\n' "- Scope: scripts/sd-ai-command-pack-*.sh (measured with kcov)"
    printf '%s\n' "- Lines: ${covered}/${total} (${pct}%)"
    printf '%s\n' "- full-check.sh's inline \`python3 - <<HEREDOC\` region is not bash-executed, so kcov excludes it; its extraction and measurement are a separate task."
    printf '%s\n' "- No coverage floor is enforced yet; this step publishes a measured baseline."
  } >>"$GITHUB_STEP_SUMMARY"
fi
