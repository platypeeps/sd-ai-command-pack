#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 2 ]; then
  printf '%s\n' "usage: check-main-push-scope.sh <before-sha> <after-sha>" >&2
  exit 2
fi

before_sha="$1"
after_sha="$2"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf '%s\n' "main-push scope: cannot resolve the Git repository root" >&2
  exit 1
}
cd "$repo_root"

if [[ "$before_sha" =~ ^0+$ ]]; then
  printf '%s\n' "main-push scope: the prior main SHA is unavailable; failing closed" >&2
  exit 1
fi
for commit in "$before_sha" "$after_sha"; do
  if ! git rev-parse --verify --quiet "$commit^{commit}" >/dev/null; then
    printf '%s\n' "main-push scope: commit $commit is unavailable; failing closed" >&2
    exit 1
  fi
done

# A pull-request merge — this repo lands non-chore work through PRs merged with
# a merge commit — is the sanctioned path for reviewed content reaching main,
# and such a commit has a second parent. Only direct, non-merge pushes are
# subject to the chore-only scope rule. Branch protection and review remain the
# primary control; this guard is the keep-honest backstop against a direct
# non-chore push, so it must not reject the merge commits it is meant to allow.
if git rev-parse --verify --quiet "$after_sha^2" >/dev/null; then
  printf '%s\n' "main-push scope: pull-request merge commit accepted"
  exit 0
fi

paths_file="$(mktemp "${TMPDIR:-/tmp}/sd-ai-command-pack-main-push.XXXXXX")"
cleanup() {
  local status=$?
  rm -f -- "$paths_file"
  return "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! git diff --no-renames --name-only -z "$before_sha" "$after_sha" -- >"$paths_file"; then
  printf '%s\n' "main-push scope: could not inspect the pushed diff; failing closed" >&2
  exit 1
fi

offenders=()
while IFS= read -r -d '' path; do
  case "$path" in
    .trellis/tasks/*|.trellis/workspace/*)
      ;;
    *)
      offenders+=("$path")
      ;;
  esac
done <"$paths_file"

if [ "${#offenders[@]}" -eq 0 ]; then
  printf '%s\n' "main-push scope: chore-only diff accepted"
  exit 0
fi

printf '%s\n' "main-push scope: direct pushes to main may only change .trellis/tasks/** or .trellis/workspace/**" >&2
printf '%s\n' "Offending paths:" >&2
for path in "${offenders[@]}"; do
  printf '  %q\n' "$path" >&2
done
printf '%s\n' "Use a pull request for this change." >&2
exit 1
