#!/usr/bin/env bash
# shellcheck disable=SC1090,SC2129
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# The repository being checked, which is not necessarily the one hosting this
# script. A thin install moves this file to the machine, where `$SCRIPT_DIR/..`
# is the agents directory rather than any checkout -- so the old derivation
# ended the run at `fatal: not a git repository` before the first check.
#
# The first two rungs are the shared shell library's, so the override name and
# the caller's-working-tree rule stay one convention rather than two:
# `sd-ai-command-pack-shell-lib.sh:172` reads SD_AI_COMMAND_PACK_REPO_ROOT (or
# an already-set REPO_ROOT) and then `git rev-parse --show-toplevel`. The third
# rung is this script's own: the library fails there, which it can afford
# because it runs after a root is established, while this is where the root
# gets established. Under a fat install invoked from inside the repository the
# second rung resolves to exactly what the third one used to return, so every
# existing caller keeps its current root.
REPO_ROOT="${SD_AI_COMMAND_PACK_REPO_ROOT:-}"
if [ -n "$REPO_ROOT" ]; then
  # Only this rung can hand back a relative path: `git rev-parse
  # --show-toplevel` and `cd ... && pwd` both answer absolute. Left relative it
  # would be re-resolved against the working directory this script later `cd`s
  # into, so every path built from it -- the targets receipt first -- would
  # point somewhere else the moment the root stopped being the caller's cwd.
  if ! REPO_ROOT="$(cd -- "$REPO_ROOT" 2>/dev/null && pwd -P)"; then
    REPO_ROOT=""
  else
    # The shared shell library reads the raw override rather than this
    # variable (`sd-ai-command-pack-shell-lib.sh:172`), so normalizing only the
    # local copy would leave the relative form live for the cache root and for
    # every child process. Put the absolute form back where it came from.
    export SD_AI_COMMAND_PACK_REPO_ROOT="$REPO_ROOT"
  fi
fi
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
fi
# errexit does not help here: bash's `cd ""` is a silent success, so an
# empty root (failed resolution above) must be rejected explicitly.
if [ -z "$REPO_ROOT" ] || ! cd -- "$REPO_ROOT"; then
  printf 'sd-ai-command-pack-full-check: cannot resolve repository root\n' >&2
  exit 1
fi

REVIEW_LOCAL_TEMP_FILES=()

cleanup_full_check_temp_files() {
  local status=$?
  local file
  if [ "${#REVIEW_LOCAL_TEMP_FILES[@]}" -gt 0 ]; then
    for file in "${REVIEW_LOCAL_TEMP_FILES[@]}"; do
      [ -n "$file" ] && rm -f -- "$file"
    done
  fi
  return "$status"
}

full_check_mktemp() {
  local pattern="$1"
  local temp_dir="${TMPDIR:-/tmp}"
  mkdir -p -- "$temp_dir"
  mktemp "$temp_dir/$pattern"
}

trap cleanup_full_check_temp_files EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

section() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

source_sd_ai_command_pack_shell_lib() {
  local lib="$SCRIPT_DIR/sd-ai-command-pack-shell-lib.sh"
  if [ ! -r "$lib" ]; then
    printf 'sd-ai-command-pack-full-check: missing shared helper library: %s\n' "$lib" >&2
    exit 1
  fi
  . "$lib"
}

source_sd_ai_command_pack_shell_lib

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

run() {
  section "$1"
  shift
  "$@"
}

gito_max_attempts() {
  positive_int_or_default "${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS:-2}" 2
}

gito_initial_retry_delay() {
  nonnegative_int_or_default "${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_DELAY_SECONDS:-30}" 30
}

gito_max_retry_delay() {
  nonnegative_int_or_default "${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_MAX_DELAY_SECONDS:-120}" 120
}

gito_command_timeout_seconds() {
  nonnegative_int_or_default "${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_TIMEOUT_SECONDS:-600}" 600
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

full_check_base_ref() {
  if configured_review_base_ref SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF; then
    return
  fi
  default_review_base_ref
}

full_check_gito_base_ref() {
  if configured_review_base_ref SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF; then
    return
  fi
  full_check_base_ref
}

detect_merge_base() {
  local base_ref
  base_ref="$(full_check_base_ref)"
  git merge-base "$base_ref" HEAD 2>/dev/null || true
}

collect_reviewable_changed_paths() {
  local base_ref="$1"
  local paths_file
  local merge_base_status=0
  paths_file="$(full_check_mktemp "sd-ai-command-pack-review-paths.XXXXXX")"
  REVIEW_LOCAL_TEMP_FILES+=("$paths_file")
  : >"$paths_file"

  if git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null; then
    set +e
    git merge-base "$base_ref" HEAD >/dev/null 2>&1
    merge_base_status=$?
    set -e
    case "$merge_base_status" in
      0)
        git diff --name-only "$base_ref"...HEAD >>"$paths_file"
        ;;
      1)
        warn "Could not find a merge base for $base_ref and HEAD; review filter will include all tracked files."
        git ls-files >>"$paths_file"
        ;;
      *)
        warn "git merge-base failed for $base_ref and HEAD with status $merge_base_status."
        return "$merge_base_status"
        ;;
    esac
  else
    warn "Could not resolve $base_ref; Gito review filter will use local changes only."
  fi

  git diff --cached --name-only >>"$paths_file"
  git diff --name-only >>"$paths_file"
  git ls-files --others --exclude-standard >>"$paths_file"

  sort -u "$paths_file" | while IFS= read -r path; do
    [ -n "$path" ] || continue
    if ! path_is_standard_review_scan_excluded "$path"; then
      printf '%s\n' "$path"
    fi
  done

  rm -f -- "$paths_file"
}

review_filter_pattern_for_path() {
  local path="$1"
  printf '%s\n' "$path"
}

review_filter_csv_from_paths() {
  local patterns_file
  patterns_file="$(full_check_mktemp "sd-ai-command-pack-review-filters.XXXXXX")"
  REVIEW_LOCAL_TEMP_FILES+=("$patterns_file")
  : >"$patterns_file"

  local path
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    review_filter_pattern_for_path "$path" >>"$patterns_file"
  done

  local patterns=()
  local pattern
  while IFS= read -r pattern; do
    [ -n "$pattern" ] || continue
    patterns+=("$pattern")
  done < <(sort -u "$patterns_file")

  rm -f -- "$patterns_file"
  # ${arr[@]+...} guards the empty-array case: bash < 4.4 (macOS ships 3.2)
  # treats "${arr[@]}" of an empty array as unbound under set -u.
  join_by_comma ${patterns[@]+"${patterns[@]}"}
}

reviewable_changed_filter_csv() {
  local base_ref="$1"
  local changed_paths_file
  changed_paths_file="$(full_check_mktemp "sd-ai-command-pack-reviewable-paths.XXXXXX")"
  REVIEW_LOCAL_TEMP_FILES+=("$changed_paths_file")
  collect_reviewable_changed_paths "$base_ref" >"$changed_paths_file"
  review_filter_csv_from_paths <"$changed_paths_file"
  rm -f -- "$changed_paths_file"
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

  local excludes
  excludes="$(review_scan_exclude_globs_csv)"
  local configured_excludes="${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_EXCLUDE:-}"
  if [ -n "$configured_excludes" ]; then
    excludes="$excludes,$configured_excludes"
  fi
  PRISM_ARGS+=(--exclude "$excludes")
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

  local has_unstaged=0
  local has_staged=0
  if ! git diff --quiet --; then
    has_unstaged=1
  fi
  if ! git diff --cached --quiet --; then
    has_staged=1
  fi

  if [ "$has_unstaged" -eq 1 ]; then
    run_prism_command "Prism review: unstaged changes" review unstaged
  fi

  if [ "$has_staged" -eq 1 ]; then
    run_prism_command "Prism review: staged changes" review staged
  fi

  if [ "$has_unstaged" -eq 1 ] || [ "$has_staged" -eq 1 ]; then
    warn "Local changes were reviewed; skipping committed branch Prism review to avoid redundant scans."
    return 0
  fi

  local merge_base
  merge_base="$(detect_merge_base)"
  if [ -z "$merge_base" ]; then
    warn "Could not resolve merge base for $(full_check_base_ref); skipping committed branch review."
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

  load_gito_pack_env
  local base_ref
  base_ref="$(full_check_gito_base_ref)"
  local out_dir="${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR:-.build/review/gito}"
  local filters_file
  local filters
  filters_file="$(full_check_mktemp "sd-ai-command-pack-review-filter-csv.XXXXXX")"
  REVIEW_LOCAL_TEMP_FILES+=("$filters_file")
  reviewable_changed_filter_csv "$base_ref" >"$filters_file"
  IFS= read -r filters <"$filters_file" || true
  rm -f -- "$filters_file"
  if [ -z "$filters" ]; then
    warn "No changed files remain after standard review-scan exclusions; skipping Gito review."
    return 0
  fi
  mkdir -p "$out_dir"

  run_gito_command "Gito review" gito review --vs "$base_ref" --filter "$filters" --out "$out_dir"
}

run_sd_ai_command_pack_scope_check() {
  # Pack helpers are siblings of this script (SCRIPT_DIR), never repository-root
  # paths, so the gate works from a vendored scripts/ directory and from a
  # plugin bin/ alike. Diagnostics name the helper, not its resolved location.
  local name="sd-ai-command-pack-review-scope.sh"
  local script="$SCRIPT_DIR/$name"
  if [ ! -f "$script" ]; then
    warn "$name not found; skipping tooling/generated review-scope check."
    return 0
  fi

  run "SD AI command pack tooling/generated scope check" bash "$script"
}

run_sd_ai_command_pack_install_audit() {
  local mode="${SD_AI_COMMAND_PACK_INSTALL_AUDIT:-1}"
  local name="sd-ai-command-pack-install-audit.py"
  local script="$SCRIPT_DIR/$name"

  if is_disabled "$mode"; then
    warn "Skipping install audit because SD_AI_COMMAND_PACK_INSTALL_AUDIT=$mode."
    return 0
  fi

  if [ ! -f "$script" ]; then
    if [ "$mode" = "required" ]; then
      printf 'Install audit is required but %s is missing.\n' "$name" >&2
      exit 127
    fi
    warn "$name not found; skipping install audit."
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

run_sd_ai_command_pack_kb_freshness_check() {
  local mode="${SD_AI_COMMAND_PACK_FULL_CHECK_KB:-auto}"
  local name="sd-ai-command-pack-update-spec-kb.py"
  local script="$SCRIPT_DIR/$name"
  local ignore_status=0

  if is_disabled "$mode"; then
    warn "Skipping Obsidian KB freshness check because SD_AI_COMMAND_PACK_FULL_CHECK_KB=$mode."
    return 0
  fi

  if [ ! -f "$script" ]; then
    if [ "$mode" = "required" ]; then
      printf 'Obsidian KB freshness check is required but %s is missing.\n' "$name" >&2
      exit 127
    fi
    warn "$name not found; skipping Obsidian KB freshness check."
    return 0
  fi

  if ! have python3; then
    if [ "$mode" = "required" ]; then
      printf 'Obsidian KB freshness check is required but python3 is not found on PATH.\n' >&2
      exit 127
    fi
    warn "python3 not found on PATH; skipping Obsidian KB freshness check."
    return 0
  fi

  if [ "$mode" != "required" ] && [ ! -e ".obsidian-kb" ] && [ ! -L ".obsidian-kb" ]; then
    warn "No generated .obsidian-kb folder; skipping Obsidian KB freshness check. Run 'python3 $script' to generate it."
    return 0
  fi

  if run "SD AI command pack Obsidian KB freshness check" python3 "$script" --check; then
    return 0
  fi

  if [ "$mode" = "required" ]; then
    printf 'Generated Obsidian KB is stale or blocked. Refresh it with: python3 %s\n' "$script" >&2
    exit 1
  fi

  if ! have git; then
    printf 'Generated Obsidian KB is stale or blocked, but git is not found on PATH; refusing automatic refresh.\n' >&2
    printf 'Install git, then verify the ignored state with: git check-ignore -q -- .obsidian-kb\n' >&2
    exit 127
  fi

  git check-ignore -q -- ".obsidian-kb" || ignore_status=$?
  if [ "$ignore_status" -eq 1 ]; then
    printf 'Generated Obsidian KB is stale or blocked, but .obsidian-kb is not ignored; refusing automatic refresh.\n' >&2
    printf 'Refresh it with: python3 %s\n' "$script" >&2
    exit 1
  fi
  if [ "$ignore_status" -ne 0 ]; then
    printf 'Generated Obsidian KB is stale or blocked, but its ignored state could not be verified; refusing automatic refresh.\n' >&2
    printf 'Verify it with: git check-ignore -q -- .obsidian-kb\n' >&2
    exit 1
  fi

  warn "Generated Obsidian KB is stale; refreshing ignored output automatically."
  if ! run "SD AI command pack Obsidian KB refresh" python3 "$script"; then
    printf 'Automatic Obsidian KB refresh failed. Retry with: python3 %s\n' "$script" >&2
    exit 1
  fi

  if ! run "SD AI command pack Obsidian KB post-refresh check" python3 "$script" --check; then
    printf 'Generated Obsidian KB is still stale or blocked after refresh. Retry with: python3 %s\n' "$script" >&2
    exit 1
  fi
}

run_sd_ai_command_pack_surface_check() {
  # Shipped-surface closure only applies inside the pack source repository
  # itself: the helper is a sibling of this script, and the generic source
  # markers (install.py, manifest.json, templates/) are what make a checkout a
  # pack source tree rather than a consumer install. Consumers skip silently.
  local name="sd-ai-command-pack-surface-check.py"
  local script="$SCRIPT_DIR/$name"
  if [ ! -f "$REPO_ROOT/install.py" ] || [ ! -f "$REPO_ROOT/manifest.json" ] || [ ! -d "$REPO_ROOT/templates" ]; then
    return 0
  fi
  if [ ! -f "$script" ]; then
    warn "$name not found; skipping shipped-surface closure check."
    return 0
  fi
  if ! have python3; then
    warn "python3 not found on PATH; skipping shipped-surface closure check."
    return 0
  fi

  run "SD shipped-surface closure" python3 "$script"
}

run_sd_ai_command_pack_pr_body_scope_check() {
  local mode="${SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK:-auto}"
  local name="sd-ai-command-pack-pr-body-scope.py"
  local script="$SCRIPT_DIR/$name"

  if is_disabled "$mode"; then
    warn "Skipping PR-body scope check because SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK=$mode."
    return 0
  fi

  if [ ! -f "$script" ]; then
    if [ "$mode" = "required" ]; then
      printf 'PR-body scope check is required but %s is missing.\n' "$name" >&2
      exit 127
    fi
    warn "$name not found; skipping PR-body scope check."
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

  local base_ref
  base_ref="$(full_check_base_ref)"
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
  paths_file="$(full_check_mktemp "sd-ai-command-pack-ci-paths.XXXXXX")"
  REVIEW_LOCAL_TEMP_FILES+=("$paths_file")
  collect_current_changed_paths "$paths_file"

  local -a changed_paths=()
  local path
  while IFS= read -r path; do
    changed_paths+=("$path")
  done <"$paths_file"

  if [ "${#changed_paths[@]}" -eq 0 ]; then
    rm -f -- "$paths_file"
    warn "No current changed paths; skipping current-diff CI classification report."
    return 0
  fi

  section "CI change classification: current diff"
  printf 'changed_paths=%s\n' "${#changed_paths[@]}"
  local status=0

  if [ "$script" = "scripts/classify_ci_changes.sh" ]; then
    warn "Running legacy $script with a changed-files list. Update to scripts/classify-ci-changes.sh with '-- path...' support before the next pack refresh."
    bash "$script" "$paths_file" || status=$?
  else
    bash "$script" -- "${changed_paths[@]}" || status=$?
  fi

  rm -f -- "$paths_file"
  return "$status"
}

run_review_preflight() {
  local mode="${SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT:-1}"
  local command="${SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND:-}"
  # The pack helper is a sibling of this script; the legacy path stays
  # repository-relative because it names a repo-owned preflight, not payload.
  local name="sd-ai-command-pack-review-preflight.mjs"
  local script="${SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_SCRIPT:-$SCRIPT_DIR/$name}"
  local legacy_script="scripts/check-review-preflight.mjs"

  if is_disabled "$mode"; then
    warn "Skipping review preflight because SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT=$mode."
    return 0
  fi

  if [ -n "$command" ]; then
    run "Review preflight" bash -c "$command"
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
  prepare_tool_cache_env || exit 5
  section "SD AI command pack full check"
  git status -sb

  run "Whitespace check: unstaged diff" git diff --check
  run "Whitespace check: staged diff" git diff --cached --check
  run_review_preflight
  run_sd_ai_command_pack_install_audit
  run_sd_ai_command_pack_kb_freshness_check
  run_sd_ai_command_pack_surface_check
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
