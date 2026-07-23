#!/usr/bin/env bash
set -euo pipefail

case "${BASH_SOURCE[0]}" in
  */*) SCRIPT_DIR="${BASH_SOURCE[0]%/*}" ;;
  *) SCRIPT_DIR="." ;;
esac
REMOTE="origin"
DRY_RUN=0
SELF_TEST=0
DELETE_REMOTE_BRANCH=1
AUTO_MERGE=1
FINISH_WORK_HEAD=""
DEPENDENCY_PR=""
MERGE_STRATEGY="${SD_AI_COMMAND_PACK_HOUSEKEEPING_MERGE_STRATEGY:-merge}"
HOUSEKEEPING_GIT_TIMEOUT_SECONDS=60
HOUSEKEEPING_GH_TIMEOUT_SECONDS=120

ACTIONS=()
ANOMALIES=()
REFS_REFRESHED=0
DEFAULT_BRANCH=""
START_BRANCH=""
GITHUB_REPO_SLUG=""
GH_REPO_ARGS=()
FIELD_SEPARATOR=$'\x1f'

usage() {
  cat <<'EOF'
Usage: bash scripts/sd-ai-command-pack-housekeeping.sh [options]

End-of-stream housekeeping for a single active Trellis development stream.

Options:
  --dry-run              Preview cleanup without running mutating git commands.
  --no-auto-merge        Do not merge an already-green open PR.
  --finish-work-head <oid> Attest that SD finish-work completed for this exact
                           commit and any resulting commits were pushed.
  --dependency-pr <number> Internal sd-update-deps mode: evaluate and merge one
                           dependency PR without Trellis finish-work evidence.
  --merge-strategy <name> Merge strategy for ready open PRs: merge, squash, or rebase. Defaults to merge.
  --keep-remote-branch   Leave the merged remote branch on GitHub.
  --remote <name>        Remote to fetch, prune, pull, and clean. Defaults to origin.
  --self-test            Verify this installed script's merge-gate contract
                         against stubbed scenarios (hermetic: no git, gh, or
                         network access) and exit.
  -h, --help             Show this help.

Environment:
  SD_AI_COMMAND_PACK_HOUSEKEEPING_MERGE_STRATEGY
                          Default merge strategy when --merge-strategy is not set.
EOF
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

source_sd_ai_command_pack_shell_lib() {
  local lib="$SCRIPT_DIR/sd-ai-command-pack-shell-lib.sh"
  if [ ! -r "$lib" ]; then
    case " $* " in
      *" --self-test "*)
        have() { command -v "$1" >/dev/null 2>&1; }
        run_command_with_timeout() {
          shift
          "$@"
        }
        return 0
        ;;
    esac
    printf 'sd-ai-command-pack-housekeeping: missing shared helper library: %s\n' "$lib" >&2
    exit 1
  fi
  # shellcheck source=scripts/sd-ai-command-pack-shell-lib.sh
  . "$lib"
}

source_sd_ai_command_pack_shell_lib "$@"

section() {
  printf '\n==> %s\n' "$*"
}

add_action() {
  ACTIONS+=("$*")
}

add_anomaly() {
  ANOMALIES+=("$*")
}

print_list() {
  local item
  if [ "$#" -eq 0 ]; then
    printf 'none\n'
    return 0
  fi
  for item in "$@"; do
    printf -- '- %s\n' "$item"
  done
}

valid_merge_strategy() {
  case "$1" in
    merge|squash|rebase)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

valid_github_repo_slug() {
  local slug="$1"
  local owner
  local name

  case "$slug" in
    ""|/*|*/|*/*/*|*" "*|*$'\t'*|*$'\n'*)
      return 1
      ;;
  esac
  owner="${slug%%/*}"
  name="${slug#*/}"
  [ -n "$owner" ] && [ -n "$name" ] && [ "$owner" != "$slug" ]
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run)
        DRY_RUN=1
        ;;
      --no-auto-merge)
        AUTO_MERGE=0
        ;;
      --finish-work-head)
        shift
        if [ "$#" -eq 0 ] || [ -z "${1:-}" ]; then
          printf 'error: --finish-work-head requires a commit OID\n' >&2
          exit 2
        fi
        # Enumerate lowercase hex digits because locale-aware ranges can treat
        # uppercase letters as members of [a-f] on older macOS Bash versions.
        case "$1" in
          *[!0123456789abcdef]*)
            printf 'error: --finish-work-head must be a full 40-character commit OID in lowercase\n' >&2
            exit 2
            ;;
        esac
        if [ "${#1}" -ne 40 ]; then
          printf 'error: --finish-work-head must be a full 40-character commit OID in lowercase\n' >&2
          exit 2
        fi
        FINISH_WORK_HEAD="$1"
        ;;
      --merge-strategy)
        shift
        if [ "$#" -eq 0 ] || [ -z "${1:-}" ]; then
          printf 'error: --merge-strategy requires a value\n' >&2
          exit 2
        fi
        if valid_merge_strategy "$1"; then
          MERGE_STRATEGY="$1"
        else
          printf 'error: --merge-strategy must be merge, squash, or rebase\n' >&2
          exit 2
        fi
        ;;
      --dependency-pr)
        shift
        if [ "$#" -eq 0 ] || ! [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]; then
          printf 'error: --dependency-pr requires a positive PR number\n' >&2
          exit 2
        fi
        DEPENDENCY_PR="$1"
        ;;
      --keep-remote-branch)
        DELETE_REMOTE_BRANCH=0
        ;;
      --self-test)
        SELF_TEST=1
        ;;
      --remote)
        shift
        if [ "$#" -eq 0 ] || [ -z "${1:-}" ]; then
          printf 'error: --remote requires a value\n' >&2
          exit 2
        fi
        case "$1" in
          -*)
            printf 'error: --remote value must not start with "-": %s\n' "$1" >&2
            exit 2
            ;;
        esac
        REMOTE="$1"
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        printf 'error: unknown option: %s\n' "$1" >&2
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
  if [ -n "$DEPENDENCY_PR" ] && [ -n "$FINISH_WORK_HEAD" ]; then
    printf 'error: --dependency-pr cannot be combined with --finish-work-head\n' >&2
    exit 2
  fi
  if [ -n "$DEPENDENCY_PR" ] && [ "$AUTO_MERGE" -eq 0 ]; then
    printf 'error: --dependency-pr cannot be combined with --no-auto-merge\n' >&2
    exit 2
  fi
}

current_branch() {
  git symbolic-ref --quiet --short HEAD 2>/dev/null || true
}

working_tree_status() {
  git status --porcelain
}

working_tree_is_clean() {
  # Fail closed: a failing `git status` (index.lock contention, filesystem
  # errors) must read as "not verifiably clean", never as clean.
  local status_output
  if ! status_output="$(working_tree_status)"; then
    return 1
  fi
  [ -z "$status_output" ]
}

run_mutating_git() {
  if [ "$DRY_RUN" -eq 1 ]; then
    add_action "would run: git $*"
    return 0
  fi
  git "$@"
}

run_network_git() {
  if [ "$DRY_RUN" -eq 1 ]; then
    add_action "would run: git $*"
    return 0
  fi
  run_command_with_timeout "$HOUSEKEEPING_GIT_TIMEOUT_SECONDS" git "$@"
}

run_gh() {
  run_command_with_timeout "$HOUSEKEEPING_GH_TIMEOUT_SECONDS" gh "$@"
}

refresh_obsidian_kb() {
  local toolchain="$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"
  local helper="$SCRIPT_DIR/sd-ai-command-pack-update-spec-kb.py"
  local refresh_status

  section "Refresh Obsidian KB"
  if [ ! -r "$toolchain" ] || [ ! -r "$helper" ]; then
    add_anomaly "Obsidian KB refresh failed because a required pack helper is missing or unreadable; restore the pack install, then run: bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-update-spec-kb.py"
    return 1
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    if bash "$toolchain" run-python -- "$helper" --dry-run; then
      refresh_status=0
    else
      refresh_status=$?
    fi
  else
    if bash "$toolchain" run-python -- "$helper"; then
      refresh_status=0
    else
      refresh_status=$?
    fi
  fi
  if [ "$refresh_status" -eq 0 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      add_action "previewed refresh of .obsidian-kb"
    else
      add_action "refreshed .obsidian-kb after finish-work"
    fi
    return 0
  fi

  add_anomaly "Obsidian KB refresh failed; resolve the reported issue, then run: bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-update-spec-kb.py"
  return 1
}

fetch_and_prune() {
  if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    add_anomaly "remote $REMOTE is not configured; skipped fetch/prune and remote checks"
    return 0
  fi

  if run_network_git fetch --prune "$REMOTE"; then
    if [ "$DRY_RUN" -eq 1 ]; then
      return 0
    fi
    REFS_REFRESHED=1
    add_action "fetched and pruned $REMOTE"
  else
    add_anomaly "git fetch --prune $REMOTE failed"
  fi
}

configure_github_repo_scope() {
  local configured_slug
  local remote_url

  configured_slug="${SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO:-}"
  GITHUB_REPO_SLUG=""
  GH_REPO_ARGS=()
  if [ -n "$configured_slug" ]; then
    if valid_github_repo_slug "$configured_slug"; then
      GITHUB_REPO_SLUG="$configured_slug"
    else
      add_anomaly "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO must be an owner/repo slug; ignored invalid override"
    fi
  fi
  if [ -z "$GITHUB_REPO_SLUG" ]; then
    remote_url="$(git remote get-url "$REMOTE" 2>/dev/null || true)"
    GITHUB_REPO_SLUG="$(github_repo_from_remote_url "$remote_url" || true)"
  fi
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    GH_REPO_ARGS=(--repo "$GITHUB_REPO_SLUG")
  fi
}

gh_pr_view() {
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    run_gh pr view "${GH_REPO_ARGS[@]}" "$@"
  else
    run_gh pr view "$@"
  fi
}

gh_pr_list() {
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    run_gh pr list "${GH_REPO_ARGS[@]}" "$@"
  else
    run_gh pr list "$@"
  fi
}

gh_issue_list() {
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    run_gh issue list "${GH_REPO_ARGS[@]}" "$@"
  else
    run_gh issue list "$@"
  fi
}

gh_pr_merge() {
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    run_gh pr merge "${GH_REPO_ARGS[@]}" "$@"
  else
    run_gh pr merge "$@"
  fi
}

detect_default_branch() {
  local symbolic
  symbolic="$(git symbolic-ref --quiet --short "refs/remotes/$REMOTE/HEAD" 2>/dev/null || true)"
  if [ -n "$symbolic" ]; then
    DEFAULT_BRANCH="${symbolic#"${REMOTE}"/}"
    return 0
  fi

  if have gh; then
    if [ -n "$GITHUB_REPO_SLUG" ]; then
      DEFAULT_BRANCH="$(run_gh repo view "$GITHUB_REPO_SLUG" --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || true)"
    else
      DEFAULT_BRANCH="$(run_gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || true)"
    fi
    if [ "$DEFAULT_BRANCH" = "null" ]; then
      # gh prints the literal string "null" with exit 0 for repos without
      # a default branch; fall through to the main/master probes instead.
      DEFAULT_BRANCH=""
    fi
    if [ -n "$DEFAULT_BRANCH" ]; then
      return 0
    fi
  fi

  if git show-ref --verify --quiet "refs/remotes/$REMOTE/main"; then
    DEFAULT_BRANCH="main"
  elif git show-ref --verify --quiet "refs/remotes/$REMOTE/master"; then
    DEFAULT_BRANCH="master"
  else
    add_anomaly "could not detect the default branch for $REMOTE"
  fi
}

github_repo_from_remote_url() {
  local url="$1"
  local slug=""

  case "$url" in
    git@github.com:*)
      slug="${url#git@github.com:}"
      ;;
    ssh://git@github.com/*)
      slug="${url#ssh://git@github.com/}"
      ;;
    https://github.com/*)
      slug="${url#https://github.com/}"
      ;;
    http://github.com/*)
      slug="${url#http://github.com/}"
      ;;
    *)
      return 1
      ;;
  esac

  slug="${slug%.git}"
  slug="${slug%/}"
  if ! valid_github_repo_slug "$slug"; then
    return 1
  fi

  printf '%s\n' "$slug"
}

switch_to_default_branch() {
  if [ -z "$DEFAULT_BRANCH" ]; then
    return 0
  fi

  if [ "$(current_branch)" = "$DEFAULT_BRANCH" ]; then
    add_action "already on $DEFAULT_BRANCH"
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    add_action "would switch to $DEFAULT_BRANCH"
    return 0
  fi

  if git show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
    if git switch "$DEFAULT_BRANCH"; then
      add_action "switched to $DEFAULT_BRANCH"
    else
      add_anomaly "failed to switch to $DEFAULT_BRANCH"
    fi
  elif git show-ref --verify --quiet "refs/remotes/$REMOTE/$DEFAULT_BRANCH"; then
    if git switch -c "$DEFAULT_BRANCH" "$REMOTE/$DEFAULT_BRANCH"; then
      add_action "created and switched to $DEFAULT_BRANCH from $REMOTE/$DEFAULT_BRANCH"
    else
      add_anomaly "failed to create $DEFAULT_BRANCH from $REMOTE/$DEFAULT_BRANCH"
    fi
  else
    add_anomaly "remote default ref $REMOTE/$DEFAULT_BRANCH does not exist"
  fi
}

fast_forward_default_branch() {
  if [ -z "$DEFAULT_BRANCH" ]; then
    return 0
  fi

  if [ "$(current_branch)" != "$DEFAULT_BRANCH" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      if git show-ref --verify --quiet "refs/remotes/$REMOTE/$DEFAULT_BRANCH"; then
        add_action "would fast-forward $DEFAULT_BRANCH from $REMOTE/$DEFAULT_BRANCH"
      else
        add_anomaly "remote default ref $REMOTE/$DEFAULT_BRANCH does not exist"
      fi
    fi
    return 0
  fi

  if ! git show-ref --verify --quiet "refs/remotes/$REMOTE/$DEFAULT_BRANCH"; then
    add_anomaly "remote default ref $REMOTE/$DEFAULT_BRANCH does not exist"
    return 0
  fi

  if run_network_git pull --ff-only "$REMOTE" "$DEFAULT_BRANCH"; then
    if [ "$DRY_RUN" -eq 1 ]; then
      return 0
    fi
    add_action "fast-forwarded $DEFAULT_BRANCH from $REMOTE/$DEFAULT_BRANCH"
  else
    add_anomaly "git pull --ff-only $REMOTE $DEFAULT_BRANCH failed"
  fi
}

view_pr_for_branch() {
  local branch="$1"
  local pr_data
  pr_data="$(
    gh_pr_view \
      --json number,state,mergedAt,url,headRefName,headRefOid \
      --jq '[.number, .state, .mergedAt, .url, .headRefName, .headRefOid] | map(if . == null then "" else tostring end) | join("\u001f")' \
      -- "$branch" \
      2>/dev/null ||
      true
  )"
  if [ -n "$pr_data" ]; then
    printf '%s\n' "$pr_data"
    return 0
  fi

  gh_pr_list --state merged --head="$branch" --limit 1 \
    --json number,state,mergedAt,url,headRefName,headRefOid \
    --jq '.[0] | select(. != null) | [.number, .state, .mergedAt, .url, .headRefName, .headRefOid] | map(if . == null then "" else tostring end) | join("\u001f")' \
    2>/dev/null ||
    true
}

evaluate_pr_eligibility() {
  local branch="$1"
  local helper="$SCRIPT_DIR/sd-ai-command-pack-pr-eligibility.py"
  local toolchain="$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"
  local output
  local status
  local -a args

  if [ ! -r "$helper" ]; then
    add_anomaly "PR eligibility evaluator is missing: $helper"
    return 1
  fi
  if [ ! -r "$toolchain" ]; then
    add_anomaly "toolchain resolver is missing: $toolchain"
    return 1
  fi

  args=(
    --repo .
    --branch "$branch"
    --remote "$REMOTE"
    --default-branch "$DEFAULT_BRANCH"
    --format shell
  )
  if [ -n "$FINISH_WORK_HEAD" ]; then
    args+=(--finish-work-head "$FINISH_WORK_HEAD")
  fi
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    args+=(--github-repository "$GITHUB_REPO_SLUG")
  fi

  if output="$(bash "$toolchain" run-python -- "$helper" "${args[@]}")"; then
    status=0
  else
    status=$?
  fi
  case "$status" in
    0|1|2) ;;
    *)
      add_anomaly "PR eligibility evaluator failed with exit $status; skipped auto-merge"
      return 1
      ;;
  esac
  if [ -z "$output" ]; then
    add_anomaly "PR eligibility evaluator returned no result; skipped auto-merge"
    return 1
  fi
  printf '%s\n' "$output"
}

evaluate_dependency_pr_eligibility() {
  local pr_number="$1"
  local helper="$SCRIPT_DIR/sd-ai-command-pack-pr-eligibility.py"
  local toolchain="$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"
  local output
  local status
  local -a args

  if [ ! -r "$helper" ]; then
    add_anomaly "PR eligibility evaluator is missing: $helper"
    return 1
  fi
  if [ ! -r "$toolchain" ]; then
    add_anomaly "toolchain resolver is missing: $toolchain"
    return 1
  fi
  args=(
    --repo .
    --dependency-pr-number "$pr_number"
    --remote "$REMOTE"
    --default-branch "$DEFAULT_BRANCH"
    --format shell
  )
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    args+=(--github-repository "$GITHUB_REPO_SLUG")
  fi
  if output="$(bash "$toolchain" run-python -- "$helper" "${args[@]}")"; then
    status=0
  else
    status=$?
  fi
  case "$status" in
    0|1|2) ;;
    *)
      add_anomaly "PR eligibility evaluator failed with exit $status for dependency PR #$pr_number"
      return 1
      ;;
  esac
  if [ -z "$output" ]; then
    add_anomaly "PR eligibility evaluator returned no result for dependency PR #$pr_number"
    return 1
  fi
  printf '%s\n' "$output"
}

merge_ready_open_pr() {
  local pr_number="$1"
  local expected_head="$2"
  local receipt_mode="${3-local-branch}"
  local local_head
  local merge_head
  local strategy_flag

  local_head="$(git rev-parse --verify HEAD)"
  merge_head="$expected_head"
  if [ "$receipt_mode" = "local-branch" ] && [ "$local_head" != "$merge_head" ]; then
    add_anomaly "local HEAD changed from eligible head $merge_head to $local_head before merge; skipped auto-merge"
    return 1
  fi
  case "$MERGE_STRATEGY" in
    merge)
      strategy_flag="--merge"
      ;;
    squash)
      strategy_flag="--squash"
      ;;
    rebase)
      strategy_flag="--rebase"
      ;;
    *)
      add_anomaly "unknown merge strategy $MERGE_STRATEGY; skipped auto-merge"
      return 1
      ;;
  esac

  if [ "$DRY_RUN" -eq 1 ]; then
    add_action "would merge PR #$pr_number with $MERGE_STRATEGY strategy"
    return 0
  fi

  if gh_pr_merge "$pr_number" "$strategy_flag" --match-head-commit "$merge_head"; then
    add_action "merged PR #$pr_number with $MERGE_STRATEGY strategy"
  else
    add_anomaly "failed to merge PR #$pr_number; resolve branch protection or check failures, then rerun housekeeping"
    return 1
  fi
}

maybe_merge_ready_dependency_pr() {
  local pr_number="$1"
  local eligibility_data
  local eligibility_status
  local _reason_codes
  local receipt_pr_number
  local pr_url
  local eligible_head
  local diagnostic

  if [ -z "$DEFAULT_BRANCH" ]; then
    add_anomaly "default branch is unknown; skipped dependency PR #$pr_number merge"
    return 0
  fi
  if [ "$START_BRANCH" != "$DEFAULT_BRANCH" ]; then
    add_anomaly "dependency PR mode requires the clean default branch $DEFAULT_BRANCH; current branch is ${START_BRANCH:-detached HEAD}"
    return 0
  fi
  if ! working_tree_is_clean; then
    add_anomaly "working tree has uncommitted changes; skipped dependency PR #$pr_number merge"
    return 0
  fi
  if ! have gh; then
    add_anomaly "gh not found; skipped dependency PR #$pr_number merge"
    return 0
  fi
  if ! valid_merge_strategy "$MERGE_STRATEGY"; then
    add_anomaly "merge strategy is invalid; skipped dependency PR #$pr_number merge"
    return 0
  fi
  if ! eligibility_data="$(evaluate_dependency_pr_eligibility "$pr_number")"; then
    return 0
  fi
  IFS="$FIELD_SEPARATOR" read -r eligibility_status _reason_codes receipt_pr_number pr_url eligible_head diagnostic <<<"$eligibility_data"
  case "$eligibility_status" in
    blocked|indeterminate)
      add_anomaly "${diagnostic:-dependency PR eligibility is $eligibility_status; skipped auto-merge}"
      return 0
      ;;
    eligible)
      if [ "$receipt_pr_number" != "$pr_number" ] || [ -z "$pr_url" ] || ! [[ "$eligible_head" =~ ^[0-9a-f]{40}$ ]]; then
        add_anomaly "PR eligibility evaluator returned incomplete eligible evidence for dependency PR #$pr_number"
        return 0
      fi
      ;;
    *)
      add_anomaly "PR eligibility evaluator returned unknown status ${eligibility_status:-empty} for dependency PR #$pr_number"
      return 0
      ;;
  esac
  add_action "dependency PR #$pr_number is green, comment-clean, mergeable, and exact-head current ($pr_url)"
  merge_ready_open_pr "$pr_number" "$eligible_head" dependency-pr || return 0
}

maybe_merge_ready_open_pr() {
  local branch="$1"
  local eligibility_data
  local eligibility_status
  local _reason_codes
  local pr_number
  local pr_url
  local eligible_head
  local diagnostic

  if [ "$AUTO_MERGE" -eq 0 ] || [ -z "$branch" ] || [ "$branch" = "$DEFAULT_BRANCH" ]; then
    return 0
  fi
  if ! have gh; then
    add_anomaly "gh not found; skipped auto-merge"
    return 0
  fi
  if ! valid_merge_strategy "$MERGE_STRATEGY"; then
    add_anomaly "merge strategy is invalid; expected merge, squash, or rebase; skipped auto-merge"
    return 0
  fi
  if [ -z "$DEFAULT_BRANCH" ]; then
    add_anomaly "default branch is unknown; skipped auto-merge"
    return 0
  fi
  if [ -z "$GITHUB_REPO_SLUG" ]; then
    # Cleanup may still resolve an already-merged PR from the local checkout.
    # Avoid inventing an open-PR eligibility anomaly before that lifecycle
    # lookup; an actually open PR remains untouched and is reported below.
    return 0
  fi

  if ! eligibility_data="$(evaluate_pr_eligibility "$branch")"; then
    return 0
  fi
  IFS="$FIELD_SEPARATOR" read -r eligibility_status _reason_codes pr_number pr_url eligible_head diagnostic <<<"$eligibility_data"
  case "$eligibility_status" in
    blocked|indeterminate)
      add_anomaly "${diagnostic:-PR eligibility is $eligibility_status; skipped auto-merge}"
      return 0
      ;;
    eligible)
      if ! [[ "$pr_number" =~ ^[0-9]+$ ]] || [ -z "$pr_url" ] || ! [[ "$eligible_head" =~ ^[0-9a-f]{40}$ ]]; then
        add_anomaly "PR eligibility evaluator returned incomplete eligible evidence; skipped auto-merge"
        return 0
      fi
      ;;
    *)
      add_anomaly "PR eligibility evaluator returned unknown status ${eligibility_status:-empty}; skipped auto-merge"
      return 0
      ;;
  esac

  add_action "PR #$pr_number is open, green, comment-clean, and matches local $branch ($pr_url)"
  merge_ready_open_pr "$pr_number" "$eligible_head" || return 0
}

cleanup_current_branch_if_merged() {
  local branch="$1"
  local pr_data
  local pr_number
  local pr_state
  local pr_merged_at
  local pr_url
  local pr_head
  local pr_head_oid
  local local_head_oid
  local ls_remote_output
  local remote_head_oid

  if [ -z "$branch" ]; then
    add_anomaly "detached HEAD; skipped branch cleanup"
    return 0
  fi
  if [ -z "$DEFAULT_BRANCH" ] || [ "$branch" = "$DEFAULT_BRANCH" ]; then
    return 0
  fi
  if ! working_tree_is_clean; then
    add_anomaly "working tree has uncommitted changes; skipped switching and branch deletion"
    return 0
  fi
  if ! have gh; then
    add_anomaly "gh not found; cannot confirm whether $branch has a merged PR"
    return 0
  fi

  pr_data="$(view_pr_for_branch "$branch")"
  if [ -z "$pr_data" ]; then
    add_anomaly "unable to resolve GitHub PR metadata for $branch; no PR was found or gh failed, so the branch was left untouched"
    return 0
  fi

  IFS="$FIELD_SEPARATOR" read -r pr_number pr_state pr_merged_at pr_url pr_head pr_head_oid <<<"$pr_data"
  if [ "$pr_state" != "MERGED" ]; then
    add_anomaly "PR #$pr_number for $branch is $pr_state, not MERGED; left the branch untouched"
    return 0
  fi
  if [ "$pr_head" != "$branch" ]; then
    add_anomaly "PR #$pr_number head is $pr_head, not $branch; left the branch untouched"
    return 0
  fi
  local_head_oid="$(git rev-parse --verify "refs/heads/$branch^{commit}")"
  if [ -n "$pr_head_oid" ] && [ "$local_head_oid" != "$pr_head_oid" ]; then
    add_anomaly "local $branch is at $local_head_oid, but merged PR #$pr_number ended at $pr_head_oid; left the branch untouched"
    return 0
  fi

  add_action "confirmed PR #$pr_number merged at $pr_merged_at ($pr_url)"
  switch_to_default_branch
  fast_forward_default_branch

  if [ "$DRY_RUN" -eq 0 ] && [ "$(current_branch)" != "$DEFAULT_BRANCH" ]; then
    add_anomaly "still on $branch; skipped branch deletion"
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    add_action "would delete local branch $branch"
  elif git show-ref --verify --quiet "refs/heads/$branch"; then
    if git branch -D -- "$branch"; then
      add_action "deleted local branch $branch"
    else
      add_anomaly "failed to delete local branch $branch"
    fi
  fi

  if [ "$DELETE_REMOTE_BRANCH" -eq 0 ]; then
    add_action "left remote branch $REMOTE/$branch because --keep-remote-branch was set"
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    add_action "would delete remote branch $REMOTE/$branch"
    return 0
  fi

  set +e
  ls_remote_output="$(run_network_git ls-remote --exit-code "$REMOTE" "refs/heads/$branch" 2>/dev/null)"
  local ls_remote_status=$?
  set -e

  if [ "$ls_remote_status" -eq 0 ]; then
    remote_head_oid="${ls_remote_output%%$'\n'*}"
    remote_head_oid="${remote_head_oid%%$'\t'*}"
    if [ -z "$remote_head_oid" ]; then
      add_anomaly "failed to read remote branch head for $REMOTE/$branch"
      return 0
    fi
    if [ -n "$pr_head_oid" ] && [ "$remote_head_oid" != "$pr_head_oid" ]; then
      add_anomaly "remote branch $REMOTE/$branch is at $remote_head_oid, but merged PR #$pr_number ended at $pr_head_oid; left the remote branch untouched"
      return 0
    fi
    if run_network_git push "$REMOTE" ":refs/heads/$branch"; then
      add_action "deleted remote branch $REMOTE/$branch"
      if run_network_git fetch --prune "$REMOTE"; then
        if [ "$DRY_RUN" -eq 0 ]; then
          REFS_REFRESHED=1
        fi
        add_action "pruned $REMOTE after remote branch deletion"
      else
        add_anomaly "deleted remote branch $REMOTE/$branch, but git fetch --prune $REMOTE failed"
      fi
    else
      add_anomaly "failed to delete remote branch $REMOTE/$branch"
    fi
  elif [ "$ls_remote_status" -eq 2 ]; then
    add_action "remote branch $REMOTE/$branch is already absent"
    # With auto-delete-head-branch enabled the remote drops the branch at
    # merge time, after the initial fetch/prune ran. Prune again so the stale
    # local tracking ref does not trip the final remote-branch-absent check.
    if git show-ref --verify --quiet "refs/remotes/$REMOTE/$branch"; then
      if run_network_git fetch --prune "$REMOTE"; then
        if [ "$DRY_RUN" -eq 0 ]; then
          REFS_REFRESHED=1
        fi
        add_action "pruned stale $REMOTE/$branch tracking ref"
      else
        add_anomaly "remote branch $REMOTE/$branch is already absent, but git fetch --prune $REMOTE failed"
      fi
    fi
  else
    add_anomaly "failed to check whether remote branch $REMOTE/$branch exists"
  fi
}

run_status_report() {
  local anomaly
  local status=0
  local status_args=(
    --repo "$PWD"
    --expect-clean
    --remote "$REMOTE"
    --source-branch "$START_BRANCH"
  )

  section "Tasks performed"
  if [ "${#ACTIONS[@]}" -eq 0 ]; then
    print_list
  else
    print_list "${ACTIONS[@]}"
  fi
  if [ -n "$DEFAULT_BRANCH" ]; then
    status_args+=(--default-branch "$DEFAULT_BRANCH")
  fi
  if [ -n "$GITHUB_REPO_SLUG" ]; then
    status_args+=(--github-repo "$GITHUB_REPO_SLUG")
  fi
  if [ "$REFS_REFRESHED" -eq 1 ]; then
    status_args+=(--refs-refreshed)
  fi
  if [ "$DELETE_REMOTE_BRANCH" -eq 0 ]; then
    status_args+=(--keep-remote-branch)
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    status_args+=(--dry-run)
  fi
  if [ "${#ANOMALIES[@]}" -gt 0 ]; then
    for anomaly in "${ANOMALIES[@]}"; do
      status_args+=(--prior-anomaly "$anomaly")
    done
  fi

  if [ ! -r "$SCRIPT_DIR/sd-ai-command-pack-status.py" ]; then
    section "Anomalies"
    if [ "${#ANOMALIES[@]}" -gt 0 ]; then
      print_list "${ANOMALIES[@]}" \
        "status collector is missing: $SCRIPT_DIR/sd-ai-command-pack-status.py"
    else
      print_list "status collector is missing: $SCRIPT_DIR/sd-ai-command-pack-status.py"
    fi
    return 1
  fi
  if [ ! -r "$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh" ]; then
    section "Anomalies"
    if [ "${#ANOMALIES[@]}" -gt 0 ]; then
      print_list "${ANOMALIES[@]}" \
        "toolchain resolver is missing: $SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"
    else
      print_list "toolchain resolver is missing: $SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"
    fi
    return 1
  fi

  bash "$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh" run-python -- \
    "$SCRIPT_DIR/sd-ai-command-pack-status.py" "${status_args[@]}" || status=$?
  return "$status"
}

# Hermetic self-test of the auto-merge gate contract. Every collaborator that
# would touch git, gh, or the network is overridden inside a subshell, so the
# scenarios exercise exactly the vendored gate logic in this file. Consumers
# run `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test` from CI to
# verify their installed copy instead of maintaining bespoke contract tests.
self_test_scenario() {
  local name="$1" expectation="$2" scenario_status="$3" scenario_diagnostic="$4"
  local default_branch="${5-main}"
  local scenario_url="${6-https://example.test/pr/153}"
  local scenario_head="${7-1111111111111111111111111111111111111111}"
  local output merged=0 subshell_status=0

  # Capture the subshell status explicitly so a scenario that dies (for
  # example on an unexpected external call) reports a named failure instead
  # of relying on the caller's AND-OR context to suppress errexit.
  output="$(
    # Guarantee hermeticity rather than assume it: with an empty PATH every
    # unstubbed external command fails loudly, and gh is stubbed to fail so
    # future gate logic cannot silently reach GitHub even if PATH leaks.
    # shellcheck disable=SC2123  # emptying the search path is the point
    PATH=''
    DEFAULT_BRANCH="$default_branch"
    AUTO_MERGE=1
    FINISH_WORK_HEAD=headoid
    MERGE_STRATEGY=merge
    GITHUB_REPO_SLUG=owner/repo
    ANOMALIES=()
    have() { return 0; }
    evaluate_pr_eligibility() {
      printf '%s\037self-test\037153\037%s\037%s\037%s\n' \
        "$scenario_status" "$scenario_url" "$scenario_head" "$scenario_diagnostic"
    }
    merge_ready_open_pr() {
      if [ "$1" != 153 ] || [ "$2" != 1111111111111111111111111111111111111111 ]; then
        printf 'self-test: merge received invalid receipt identity\n' >&2
        return 1
      fi
      printf 'SELF_TEST_MERGE_EVENT\n'
      return 0
    }
    maybe_merge_ready_open_pr feature
    printf 'SELF_TEST_ANOMALIES=%s\n' "${ANOMALIES[*]-}"
  )" || subshell_status=$?

  if [ "$subshell_status" -ne 0 ]; then
    printf 'self-test: %s: FAIL (scenario subshell exited %s)\n' \
      "$name" "$subshell_status" >&2
    return 1
  fi

  case "$output" in
    *SELF_TEST_MERGE_EVENT*) merged=1 ;;
  esac
  local anomalies="${output#*SELF_TEST_ANOMALIES=}"

  if [ "$expectation" = merge ]; then
    if [ "$merged" -eq 1 ] && [ -z "$anomalies" ]; then
      printf 'self-test: %s: ok\n' "$name"
      return 0
    fi
  else
    case "$anomalies" in
      *"skipped auto-merge"*)
        if [ "$merged" -eq 0 ]; then
          printf 'self-test: %s: ok\n' "$name"
          return 0
        fi
        ;;
    esac
  fi
  printf 'self-test: %s: FAIL (expected %s; merged=%s anomalies=%s)\n' \
    "$name" "$expectation" "$merged" "$anomalies" >&2
  return 1
}

run_self_test() {
  local failures=0

  self_test_scenario "eligible receipt merges" merge eligible "eligible" || failures=$((failures + 1))
  self_test_scenario "blocked receipt refuses" refuse blocked "checks blocked; skipped auto-merge" || failures=$((failures + 1))
  self_test_scenario "indeterminate receipt refuses" refuse indeterminate "review state unavailable; skipped auto-merge" || failures=$((failures + 1))
  self_test_scenario "incomplete eligible receipt refuses" refuse eligible "eligible" main "" || failures=$((failures + 1))
  self_test_scenario "unknown receipt status refuses" refuse unknown "unknown status; skipped auto-merge" || failures=$((failures + 1))
  self_test_scenario "unknown default branch refuses" refuse eligible "eligible" "" || failures=$((failures + 1))

  # Retain the original installed self-test labels as consumer-facing contract
  # aliases while the evaluator owns their detailed fixture coverage.
  self_test_scenario "finish-work head required" refuse blocked "finish-work evidence missing; skipped auto-merge" || failures=$((failures + 1))
  self_test_scenario "stale finish-work head refuses" refuse blocked "finish-work evidence stale; skipped auto-merge" || failures=$((failures + 1))
  self_test_scenario "green executed checks merge" merge eligible "eligible" || failures=$((failures + 1))

  if [ "$failures" -ne 0 ]; then
    printf 'self-test: %s scenario(s) FAILED\n' "$failures" >&2
    return 1
  fi
  printf 'self-test: all scenarios passed\n'
  return 0
}

main() {
  local repo_root

  parse_args "$@"
  if [ "$SELF_TEST" -eq 1 ]; then
    run_self_test
    exit $?
  fi
  if ! have git; then
    printf 'error: git not found on PATH\n' >&2
    exit 2
  fi
  if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    printf 'error: not inside a git repository\n' >&2
    exit 2
  fi
  cd "$repo_root"

  section "SD AI command pack housekeeping"
  printf 'repo: %s\n' "$repo_root"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'mode: dry-run\n'
  fi

  START_BRANCH="$(current_branch)"
  printf 'start branch: %s\n' "${START_BRANCH:-detached HEAD}"

  if [ -z "$DEPENDENCY_PR" ]; then
    if ! refresh_obsidian_kb; then
      run_status_report
      return 1
    fi
  else
    add_action "skipped post-finish Obsidian KB refresh for dependency PR mode"
  fi

  configure_github_repo_scope
  fetch_and_prune
  detect_default_branch
  if [ -n "$DEFAULT_BRANCH" ]; then
    printf 'default branch: %s\n' "$DEFAULT_BRANCH"
  fi

  if [ -n "$DEPENDENCY_PR" ]; then
    maybe_merge_ready_dependency_pr "$DEPENDENCY_PR"
    fast_forward_default_branch
  elif [ "$START_BRANCH" = "$DEFAULT_BRANCH" ]; then
    fast_forward_default_branch
  else
    maybe_merge_ready_open_pr "$START_BRANCH"
    cleanup_current_branch_if_merged "$START_BRANCH"
  fi

  run_status_report
}

main "$@"
