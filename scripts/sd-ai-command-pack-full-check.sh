#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

section() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

is_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|required) return 0 ;;
    *) return 1 ;;
  esac
}

is_disabled() {
  case "${1:-}" in
    0|false|FALSE|no|NO|skip|none) return 0 ;;
    *) return 1 ;;
  esac
}

have() {
  command -v "$1" >/dev/null 2>&1
}

run() {
  section "$1"
  shift
  "$@"
}

package_has_script() {
  local script_name="$1"
  have node || return 1
  SCRIPT_NAME="$script_name" node -e '
const fs = require("fs");
const scriptName = process.env.SCRIPT_NAME;
const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
process.exit(pkg.scripts && Object.prototype.hasOwnProperty.call(pkg.scripts, scriptName) ? 0 : 1);
' >/dev/null 2>&1
}

detect_merge_base() {
  local base_ref="${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}"
  git merge-base "$base_ref" HEAD 2>/dev/null || true
}

build_prism_args() {
  PRISM_ARGS=()

  local fail_on="${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_FAIL_ON:-high}"
  if [ -n "$fail_on" ]; then
    PRISM_ARGS+=(--fail-on "$fail_on")
  fi

  local max_findings="${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_MAX_FINDINGS:-}"
  if [ -n "$max_findings" ]; then
    PRISM_ARGS+=(--max-findings "$max_findings")
  fi

  local rules="${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_RULES:-}"
  if [ -z "$rules" ]; then
    if [ -f ".prism/rules.json" ]; then
      rules=".prism/rules.json"
    elif [ -f "prism-rules.json" ]; then
      rules="prism-rules.json"
    fi
  fi
  if [ -n "$rules" ] && [ -f "$rules" ]; then
    PRISM_ARGS+=(--rules "$rules")
  fi
}

run_prism_command() {
  local label="$1"
  shift
  local mode="${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM:-auto}"
  PRISM_ARGS=()
  build_prism_args

  section "$label"
  set +e
  prism "$@" "${PRISM_ARGS[@]}"
  local status=$?
  set -e

  case "$status" in
    0)
      return 0
      ;;
    1)
      printf 'Prism found findings at or above the configured threshold.\n' >&2
      exit 1
      ;;
    3|4)
      local reason="provider authentication/configuration"
      if [ "$status" = "4" ]; then
        reason="provider/model configuration"
      fi
      if [ "$mode" = "required" ]; then
        printf 'Prism is required but %s failed with exit code %s.\n' "$reason" "$status" >&2
        exit "$status"
      fi
      warn "Prism $reason failed with exit code $status; continuing because Prism is optional by default."
      return 0
      ;;
    *)
      printf 'Prism failed with exit code %s.\n' "$status" >&2
      exit "$status"
      ;;
  esac
}

run_prism_reviews() {
  local mode="${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM:-auto}"
  if is_disabled "$mode"; then
    warn "Skipping Prism review because SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=$mode."
    return 0
  fi
  if ! have prism; then
    if [ "$mode" = "required" ]; then
      printf 'Prism is required but not found on PATH.\n' >&2
      exit 127
    fi
    warn "Prism not found on PATH; skipping local AI review."
    return 0
  fi

  if ! git diff --quiet --; then
    run_prism_command "Prism review: unstaged changes" review unstaged
  fi

  if ! git diff --cached --quiet --; then
    run_prism_command "Prism review: staged changes" review staged
  fi

  local merge_base
  merge_base="$(detect_merge_base)"
  if [ -z "$merge_base" ]; then
    warn "Could not resolve merge base for ${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}; skipping committed branch review."
    return 0
  fi

  if git diff --quiet "$merge_base"..HEAD --; then
    warn "No committed branch diff since $merge_base; skipping Prism range review."
    return 0
  fi

  run_prism_command "Prism review: committed branch diff" review range "$merge_base..HEAD"
}

run_gito_review() {
  local mode="${SD_AI_COMMAND_PACK_FULL_CHECK_GITO:-0}"
  if ! is_enabled "$mode"; then
    warn "Skipping Gito review. Set SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1 to enable it."
    return 0
  fi
  if ! have gito; then
    if [ "$mode" = "required" ]; then
      printf 'Gito is required but not found on PATH.\n' >&2
      exit 127
    fi
    warn "Gito not found on PATH; skipping Gito review."
    return 0
  fi

  local base_ref="${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF:-${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}}"
  local out_dir="${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR:-.build/review/gito}"
  mkdir -p "$out_dir"

  run "Gito review" gito review --vs "$base_ref" --out "$out_dir"
}

run_sd_ai_command_pack_scope_check() {
  local script="scripts/sd-ai-command-pack-review-scope.sh"
  if [ ! -f "$script" ]; then
    warn "$script not found; skipping tooling/generated review-scope check."
    return 0
  fi

  run "SD AI command pack tooling/generated scope check" bash "$script"
}

run_sd_ai_command_pack_install_audit() {
  local mode="${SD_AI_COMMAND_PACK_INSTALL_AUDIT:-1}"
  local script="scripts/sd-ai-command-pack-install-audit.py"

  if is_disabled "$mode"; then
    warn "Skipping install audit because SD_AI_COMMAND_PACK_INSTALL_AUDIT=$mode."
    return 0
  fi

  if [ ! -f "$script" ]; then
    if [ "$mode" = "required" ]; then
      printf 'Install audit is required but %s is missing.\n' "$script" >&2
      exit 127
    fi
    warn "$script not found; skipping install audit."
    return 0
  fi

  if ! have python3; then
    if [ "$mode" = "required" ]; then
      printf 'Install audit is required but python3 is not found on PATH.\n' >&2
      exit 127
    fi
    warn "python3 not found on PATH; skipping install audit."
    return 0
  fi

  run "SD AI command pack install audit" python3 "$script"
}

run_sd_ai_command_pack_pr_body_scope_check() {
  local mode="${SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK:-auto}"
  local script="scripts/sd-ai-command-pack-pr-body-scope.py"

  if is_disabled "$mode"; then
    warn "Skipping PR-body scope check because SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK=$mode."
    return 0
  fi

  if [ ! -f "$script" ]; then
    if [ "$mode" = "required" ]; then
      printf 'PR-body scope check is required but %s is missing.\n' "$script" >&2
      exit 127
    fi
    warn "$script not found; skipping PR-body scope check."
    return 0
  fi

  if ! have python3; then
    if [ "$mode" = "required" ]; then
      printf 'PR-body scope check is required but python3 is not found on PATH.\n' >&2
      exit 127
    fi
    warn "python3 not found on PATH; skipping PR-body scope check."
    return 0
  fi

  run "SD AI command pack PR-body scope check" python3 "$script"
}

collect_current_changed_paths() {
  local output_file="$1"
  : >"$output_file"

  local base_ref="${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}"
  if git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null; then
    git diff --name-only "$base_ref"...HEAD >>"$output_file"
  else
    warn "Could not resolve $base_ref; CI classification report will use local changes only."
  fi

  git diff --cached --name-only >>"$output_file"
  git diff --name-only >>"$output_file"
  git ls-files --others --exclude-standard >>"$output_file"
  sort -u "$output_file" -o "$output_file"
}

resolve_ci_classifier_script() {
  if [ -f "scripts/classify-ci-changes.sh" ]; then
    printf '%s\n' "scripts/classify-ci-changes.sh"
    return 0
  fi
  if [ -f "scripts/classify_ci_changes.sh" ]; then
    warn "Using legacy scripts/classify_ci_changes.sh; prefer scripts/classify-ci-changes.sh with '-- path...' support."
    printf '%s\n' "scripts/classify_ci_changes.sh"
    return 0
  fi
  return 1
}

run_ci_classification_report() {
  local script
  if ! script="$(resolve_ci_classifier_script)"; then
    warn "No scripts/classify-ci-changes.sh or scripts/classify_ci_changes.sh found; skipping current-diff CI classification report."
    return 0
  fi

  local paths_file
  paths_file="$(mktemp "${TMPDIR:-/tmp}/sd-ai-command-pack-ci-paths.XXXXXX")"
  collect_current_changed_paths "$paths_file"

  local -a changed_paths=()
  local path
  while IFS= read -r path; do
    changed_paths+=("$path")
  done <"$paths_file"

  if [ "${#changed_paths[@]}" -eq 0 ]; then
    rm -f "$paths_file"
    warn "No current changed paths; skipping current-diff CI classification report."
    return 0
  fi

  section "CI change classification: current diff"
  printf 'changed_paths=%s\n' "${#changed_paths[@]}"
  local status=0
  bash "$script" -- "${changed_paths[@]}" || status=$?
  if [ "$status" -eq 2 ]; then
    warn "$script did not accept explicit '-- path...' input; retrying with a changed-files list. Update the classifier to support '-- path...' before the next pack refresh."
    status=0
    bash "$script" "$paths_file" || status=$?
  fi
  rm -f "$paths_file"
  return "$status"
}

run_review_preflight() {
  local mode="${SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT:-1}"
  local command="${SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND:-}"
  local script="${SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_SCRIPT:-scripts/sd-ai-command-pack-review-preflight.mjs}"
  local legacy_script="scripts/check-review-preflight.mjs"

  if is_disabled "$mode"; then
    warn "Skipping review preflight because SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT=$mode."
    return 0
  fi

  if [ -n "$command" ]; then
    run "Review preflight" bash -lc "$command"
    return 0
  fi

  if ! have node; then
    if [ "$mode" = "required" ]; then
      printf 'Review preflight is required but Node.js is not found on PATH.\n' >&2
      exit 127
    fi
    warn "Node.js not found on PATH; JavaScript review preflight is unavailable; skipping review preflight."
    return 0
  fi

  local ran=0
  if [ -f "$script" ]; then
    run "SD AI command pack review preflight" node "$script"
    ran=1
  fi

  if [ -f "$legacy_script" ] && [ "$legacy_script" != "$script" ]; then
    run "Repo-local review preflight" node "$legacy_script"
    ran=1
  fi

  if [ "$ran" -eq 1 ]; then
    return 0
  fi

  if [ "$mode" = "required" ]; then
    printf 'Review preflight is required but no command is configured and neither %s nor %s exists.\n' "$script" "$legacy_script" >&2
    exit 127
  fi

  warn "$script and $legacy_script not found; skipping review preflight."
}

main() {
  section "SD AI command pack full check"
  git status -sb

  run "Whitespace check: unstaged diff" git diff --check
  run "Whitespace check: staged diff" git diff --cached --check
  run_review_preflight
  run_sd_ai_command_pack_install_audit
  run_sd_ai_command_pack_scope_check
  run_sd_ai_command_pack_pr_body_scope_check
  run_ci_classification_report

  local skip_package_scripts="${SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS:-0}"
  if [ -f "package.json" ] && ! is_enabled "$skip_package_scripts"; then
    local runner="${SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER:-npm}"
    local scripts="${SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_SCRIPTS:-typecheck lint test:unit test:integration build test:e2e}"

    if ! have "$runner"; then
      warn "Package runner $runner not found on PATH; skipping package-script checks."
    elif ! have node; then
      warn "Node.js not found on PATH; cannot inspect package.json scripts; skipping package-script checks."
    else
      local script_name
      # Disable globbing so a script name in the space-separated list cannot be
      # expanded as a filesystem glob; keep ordinary IFS word-splitting.
      set -f
      for script_name in $scripts; do
        if package_has_script "$script_name"; then
          run "Package script: $script_name" "$runner" run "$script_name"
        else
          warn "package.json has no script named $script_name; skipping."
        fi
      done
      set +f
    fi
  else
    warn "No package.json found, or package-script checks disabled; skipping package-script checks."
  fi

  run_prism_reviews
  run_gito_review

  section "Full check complete"
}

if [ "${SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE:-0}" != "1" ]; then
  main "$@"
fi
