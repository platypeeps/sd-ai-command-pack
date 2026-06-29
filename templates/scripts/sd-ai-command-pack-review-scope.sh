#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGETS_FILE="${SD_AI_COMMAND_PACK_TARGETS_FILE:-$REPO_ROOT/.sd-ai-command-pack/installed-targets.txt}"
BASE_REF="${SD_AI_COMMAND_PACK_SCOPE_BASE_REF:-${SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF:-origin/main}}"
MODE="${SD_AI_COMMAND_PACK_SCOPE_CHECK:-auto}"
GH_MODE="${SD_AI_COMMAND_PACK_SCOPE_CHECK_GH:-auto}"
scope_categories=()

warn() {
  printf 'warning: %s\n' "$*" >&2
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

is_disabled() {
  case "${1:-}" in
    0|false|FALSE|no|NO|skip|none) return 0 ;;
    *) return 1 ;;
  esac
}

is_required() {
  case "${1:-}" in
    required|1|true|TRUE|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

have() {
  command -v "$1" >/dev/null 2>&1
}

has_ref() {
  git rev-parse --verify --quiet "$1^{commit}" >/dev/null
}

collect_changed_files() {
  if has_ref "$BASE_REF"; then
    git diff --name-only "$BASE_REF"...HEAD
  else
    warn "Could not resolve $BASE_REF; copied-file scope check will use local changes only."
  fi

  git diff --cached --name-only
  git diff --name-only
  git ls-files --others --exclude-standard
}

is_trellis_runtime_path() {
  local path="$1"

  case "$path" in
    .trellis/scripts/*|.trellis/agents/*|.cursor/hooks.json|.cursor/hooks/*|.github/hooks/trellis.json|.opencode/lib/trellis-context.js)
      return 0
      ;;
    .github/prompts/continue.prompt.md|.github/prompts/finish-work.prompt.md)
      return 0
      ;;
  esac

  if [[ "$path" =~ ^\.(agents|claude|cursor|gemini|github|opencode)/skills/trellis-[^/]+/ ]]; then
    return 0
  fi

  if [[ "$path" =~ ^\.cursor/commands/trellis-[^/]+\.md$ ]]; then
    return 0
  fi

  if [[ "$path" =~ ^\.(claude|gemini|opencode)/commands/trellis/ ]]; then
    return 0
  fi

  if [[ "$path" =~ ^\.(claude|cursor|gemini|opencode)/agents/trellis-[^/]+\.md$ ]]; then
    return 0
  fi

  if [[ "$path" =~ ^\.github/agents/trellis-[^/]+\.agent\.md$ ]]; then
    return 0
  fi

  return 1
}

is_pack_target_path() {
  local path="$1"

  [[ -f "$TARGETS_FILE" ]] || return 1
  grep -Fxq -- "$path" "$TARGETS_FILE"
}

is_copied_review_scope_path() {
  local path="$1"

  if is_pack_target_path "$path" || is_trellis_runtime_path "$path"; then
    return 0
  fi

  return 1
}

is_repository_map_scope_path() {
  local path="$1"

  case "$path" in
    docs/repomix-map.md|scripts/update_repomix)
      return 0
      ;;
  esac

  return 1
}

is_trellis_journal_scope_path() {
  local path="$1"

  case "$path" in
    .trellis/workspace/*/journal-*.md|.trellis/workspace/*/index.md)
      return 0
      ;;
  esac

  return 1
}

github_pr_body_mentions_scope() {
  local body="$1"

  grep -Eiq '(^|[[:space:]])(Tooling/generated scope|Generated/tooling scope|Copied/generated scope):' <<<"$body"
}

check_pr_body_scope() {
  local scoped_count="$1"

  if [[ "$scoped_count" -eq 0 ]]; then
    return 0
  fi

  if is_disabled "$GH_MODE"; then
    return 0
  fi

  if [ "${SD_AI_COMMAND_PACK_SCOPE_PR_BODY+x}" ] || [ "${REVIEW_PREFLIGHT_PR_BODY+x}" ]; then
    local explicit_body="${SD_AI_COMMAND_PACK_SCOPE_PR_BODY-${REVIEW_PREFLIGHT_PR_BODY-}}"
    if ! github_pr_body_mentions_scope "$explicit_body"; then
      fail "tooling/generated files changed, but the provided PR body does not include a Tooling/generated scope: section"
    fi
    return 0
  fi

  if ! have gh; then
    if is_required "$GH_MODE"; then
      fail "gh is required for tooling/generated PR scope checks but is not on PATH"
    fi
    warn "gh not found; skipping tooling/generated PR scope body check."
    return 0
  fi

  local pr_json
  if ! pr_json="$(gh pr view --json body,title,url 2>/dev/null)"; then
    if is_required "$GH_MODE"; then
      fail "gh could not resolve the current PR for tooling/generated scope checks"
    fi
    warn "No current PR found; skipping tooling/generated PR scope body check."
    return 0
  fi

  # Isolate the PR body so the scope heading is matched against the body only,
  # never the title or url. Without a JSON parser, skip rather than grep the raw
  # JSON blob, which would risk a false pass on a heading-like title or url.
  local pr_body
  if have python3; then
    pr_body="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("body") or "")' <<<"$pr_json")"
  elif have jq; then
    pr_body="$(jq -r '.body // ""' <<<"$pr_json")"
  else
    if is_required "$GH_MODE"; then
      fail "tooling/generated scope check requires python3 or jq to parse the PR body, but neither is on PATH"
    fi
    warn "Neither python3 nor jq found; cannot parse the PR body, skipping tooling/generated PR scope body check."
    return 0
  fi

  if ! github_pr_body_mentions_scope "$pr_body"; then
    fail "tooling/generated files changed, but the PR body does not include a Tooling/generated scope: section"
  fi
}

add_category() {
  local category="$1"
  local existing

  if [[ "${#scope_categories[@]}" -gt 0 ]]; then
    for existing in "${scope_categories[@]}"; do
      if [[ "$existing" == "$category" ]]; then
        return 0
      fi
    done
  fi

  scope_categories+=("$category")
}

main() {
  if is_disabled "$MODE"; then
    warn "Skipping tooling/generated review-scope check because SD_AI_COMMAND_PACK_SCOPE_CHECK=$MODE."
    return 0
  fi

  cd "$REPO_ROOT"

  local changed_file scoped_file scoped_count=0
  local scoped_changes=()
  scope_categories=()
  while IFS= read -r changed_file; do
    [[ -n "$changed_file" ]] || continue
    if is_copied_review_scope_path "$changed_file"; then
      scoped_changes+=("$changed_file")
      scoped_count=$((scoped_count + 1))
      add_category "copied/generated Trellis or sd-ai-command-pack files"
    elif is_repository_map_scope_path "$changed_file"; then
      scoped_changes+=("$changed_file")
      scoped_count=$((scoped_count + 1))
      add_category "known repository-map files"
    elif is_trellis_journal_scope_path "$changed_file"; then
      scoped_changes+=("$changed_file")
      scoped_count=$((scoped_count + 1))
      add_category "Trellis workspace journal/index files"
    fi
  done < <(collect_changed_files | sed '/^$/d' | sort -u)

  if [[ "$scoped_count" -eq 0 ]]; then
    return 0
  fi

  printf 'info: Tooling/generated review-scope files changed; review local integration, wiring, provenance, and secrets only.\n'
  printf 'info: Scope categories:\n'
  local category
  for category in "${scope_categories[@]}"; do
    printf '  - %s\n' "$category"
  done
  printf 'info: Changed scope files:\n'
  for scoped_file in "${scoped_changes[@]}"; do
    printf '  - %s\n' "$scoped_file"
  done

  check_pr_body_scope "$scoped_count"
}

main "$@"
