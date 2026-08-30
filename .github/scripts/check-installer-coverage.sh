#!/usr/bin/env bash
# Installer coverage gate: 100% line and branch over the installer surface.
#
# The measured set is enumerated from git at run time rather than written here
# as a glob. A literal glob drifts in two directions and the gate reports 100%
# through both: a new module lands outside the pattern and is never measured,
# or code is deleted and the same green 100% then certifies a fraction of what
# it used to. Enumeration closes the first. MIN_FILES closes the second: the
# floor has to be lowered by hand, so shrinking what 100% means is a visible
# edit in a diff rather than a side effect of deleting a file.
#
# The floor is not a target to raise eagerly. Set it to the number of files the
# surface legitimately has; when a step intentionally removes installer code --
# the step-3 sub-PR 3e replaces this surface entirely (R11-D6) -- lower it in
# that pull request, where a reviewer can see the scope change.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

MIN_FILES=17

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

# Enumerate first and check the status separately: inside a pipeline or a
# command substitution a git failure would be masked by the consumer's exit
# code, and an empty list would then read as "nothing to measure" rather than
# as the error it is.
tracked_list="$(mktemp)"
trap 'rm -f "$tracked_list"' EXIT

if ! git ls-files -- 'install.py' 'installer/*.py' >"$tracked_list"; then
  printf 'error: git ls-files failed; cannot enumerate the installer surface.\n' >&2
  exit 1
fi

file_count="$(wc -l <"$tracked_list" | tr -d ' ')"

if [ "$file_count" -lt "$MIN_FILES" ]; then
  printf 'error: installer surface is %s tracked file(s), below the declared floor of %s.\n' \
    "$file_count" "$MIN_FILES" >&2
  printf 'A 100%% gate over a shrunken surface certifies less while still reporting green.\n' >&2
  printf 'If the removal is intended, lower MIN_FILES in this script in the same pull request.\n' >&2
  exit 1
fi

include=""
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if [ -z "$include" ]; then
    include="$path"
  else
    include="$include,$path"
  fi
done <"$tracked_list"

printf 'diagnostic: installer coverage over %s tracked file(s) (floor %s)\n' \
  "$file_count" "$MIN_FILES" >&2

"$PYTHON_BIN" -m coverage report --include="$include" --fail-under=100
