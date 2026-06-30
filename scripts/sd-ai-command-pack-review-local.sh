#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

OVERALL_STATUS=0

section() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

have() {
  command -v "$1" >/dev/null 2>&1
}

is_disabled() {
  case "${1:-}" in
    0|false|FALSE|no|NO|skip|none) return 0 ;;
    *) return 1 ;;
  esac
}

record_status() {
  local label="$1"
  local status="$2"
  if [ "$status" -ne 0 ]; then
    warn "$label exited with status $status."
    OVERALL_STATUS=1
  fi
}

run_command() {
  local label="$1"
  shift
  section "$label"
  "$@"
  local status=$?
  record_status "$label" "$status"
}

tool_env_key() {
  printf '%s' "$1" \
    | tr '[:lower:]' '[:upper:]' \
    | sed 's/[^A-Z0-9_]/_/g'
}

configured_command_for_tool() {
  local tool="$1"
  local key
  key="$(tool_env_key "$tool")"
  local var_name="SD_AI_COMMAND_PACK_REVIEW_LOCAL_${key}_COMMAND"
  printf '%s' "${!var_name:-}"
}

detect_merge_base() {
  local base_ref="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_BASE_REF:-${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}}"
  git merge-base "$base_ref" HEAD 2>/dev/null || true
}

build_prism_args() {
  PRISM_ARGS=()

  local fail_on="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_FAIL_ON:-${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_FAIL_ON:-high}}"
  if [ -n "$fail_on" ]; then
    PRISM_ARGS+=(--fail-on "$fail_on")
  fi

  local max_findings="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_MAX_FINDINGS:-${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_MAX_FINDINGS:-}}"
  if [ -n "$max_findings" ]; then
    PRISM_ARGS+=(--max-findings "$max_findings")
  fi

  local rules="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_RULES:-${SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_RULES:-}}"
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
  section "$label"
  prism "$@" "${PRISM_ARGS[@]}"
  local status=$?

  case "$status" in
    0)
      return 0
      ;;
    1)
      warn "$label reported findings at or above the configured threshold."
      OVERALL_STATUS=1
      ;;
    3|4)
      warn "$label could not complete because Prism provider authentication or configuration failed with exit code $status."
      OVERALL_STATUS=1
      ;;
    *)
      record_status "$label" "$status"
      ;;
  esac
}

run_prism_reviews() {
  local mode="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_MODE:-required}"
  if is_disabled "$mode"; then
    warn "Skipping Prism review because SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_MODE=$mode."
    return
  fi
  if ! have prism; then
    warn "Prism is required for sd-review-local but was not found on PATH."
    OVERALL_STATUS=1
    return
  fi

  build_prism_args

  local ran=0
  if ! git diff --quiet --; then
    ran=1
    run_prism_command "Prism review: unstaged changes" review unstaged
  fi

  if ! git diff --cached --quiet --; then
    ran=1
    run_prism_command "Prism review: staged changes" review staged
  fi

  local merge_base
  merge_base="$(detect_merge_base)"
  if [ -n "$merge_base" ] && ! git diff --quiet "$merge_base"..HEAD --; then
    ran=1
    run_prism_command "Prism review: committed branch diff" review range "$merge_base..HEAD"
  elif [ -z "$merge_base" ]; then
    warn "Could not resolve merge base for ${SD_AI_COMMAND_PACK_REVIEW_LOCAL_BASE_REF:-${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}}; skipping Prism range review."
  fi

  if [ "$ran" -eq 0 ]; then
    warn "No unstaged, staged, or committed branch diff found for Prism review."
  fi
}

run_gito_review() {
  local mode="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MODE:-required}"
  if is_disabled "$mode"; then
    warn "Skipping Gito review because SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MODE=$mode."
    return
  fi
  if ! have gito; then
    warn "Gito is required for sd-review-local but was not found on PATH."
    OVERALL_STATUS=1
    return
  fi

  local base_ref="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF:-${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF:-${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}}}"
  local out_dir="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_OUT_DIR:-${SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR:-.build/review/gito}}"
  mkdir -p "$out_dir"
  run_command "Gito review" gito review --vs "$base_ref" --out "$out_dir"
}

run_custom_tool() {
  local tool="$1"
  local command="$2"
  run_command "Local review: $tool" bash -lc "$command"
}

raw_tools="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS:-prism gito}"
if [ "$#" -gt 0 ]; then
  raw_tools="$*"
fi
raw_tools="${raw_tools//,/ }"
read -r -a REQUESTED_TOOLS <<< "$raw_tools"

if [ "${#REQUESTED_TOOLS[@]}" -eq 0 ]; then
  warn "No local review tools requested."
  exit 2
fi

NEED_PRISM=0
NEED_GITO=0
CUSTOM_TOOL_NAMES=()
CUSTOM_TOOL_COMMANDS=()

for raw_tool in "${REQUESTED_TOOLS[@]}"; do
  [ -n "$raw_tool" ] || continue
  tool="$(printf '%s' "$raw_tool" | tr '[:upper:]' '[:lower:]')"
  case "$tool" in
    all|default)
      NEED_PRISM=1
      NEED_GITO=1
      continue
      ;;
  esac

  configured_command="$(configured_command_for_tool "$tool")"
  if [ -n "$configured_command" ]; then
    CUSTOM_TOOL_NAMES+=("$tool")
    CUSTOM_TOOL_COMMANDS+=("$configured_command")
    continue
  fi

  case "$tool" in
    prism)
      NEED_PRISM=1
      ;;
    gito)
      NEED_GITO=1
      ;;
    *)
      key="$(tool_env_key "$tool")"
      warn "No command configured for local review tool '$tool'. Set SD_AI_COMMAND_PACK_REVIEW_LOCAL_${key}_COMMAND."
      OVERALL_STATUS=2
      ;;
  esac
done

if [ "$NEED_PRISM" -eq 1 ]; then
  run_prism_reviews
fi

if [ "$NEED_GITO" -eq 1 ]; then
  run_gito_review
fi

for index in "${!CUSTOM_TOOL_NAMES[@]}"; do
  run_custom_tool "${CUSTOM_TOOL_NAMES[$index]}" "${CUSTOM_TOOL_COMMANDS[$index]}"
done

if [ "$OVERALL_STATUS" -eq 0 ]; then
  printf '\nLocal review providers completed without reported findings.\n'
else
  printf '\nLocal review providers reported findings, failures, or missing configuration.\n' >&2
fi

exit "$OVERALL_STATUS"
