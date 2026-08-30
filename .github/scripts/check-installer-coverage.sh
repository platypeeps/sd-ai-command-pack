#!/usr/bin/env bash
# Installer coverage gate: 100% line and branch over the installer surface.
#
# The measured set is enumerated from git at run time rather than written here
# as a glob. A literal glob drifts in two directions and the gate reports 100%
# through both: a new module lands outside the pattern and is never measured,
# or code is deleted and the same green 100% then certifies a fraction of what
# it used to. Enumeration closes the first. A declared floor closes the second:
# the floor has to be lowered by hand, so shrinking what 100% means is a visible
# edit in a diff rather than a side effect of deleting a file.
#
# Step 3e changed which floor does that work, and why. Until 3e the installer
# was `install.py` plus seventeen `installer/` modules, so counting files caught
# a module vanishing. The machine-scope installer is one file, and a floor of
# "at least one file" catches nothing at all -- the surface can be gutted to a
# stub and still satisfy it. So the floor moved to statements, which is what can
# actually shrink now. MIN_FILES survives as the cheaper of the two checks: it
# is what fails, with a readable message, if the file is deleted outright.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

MIN_FILES=1
MIN_STATEMENTS=450

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
report_file="$(mktemp)"
trap 'rm -f "$tracked_list" "$report_file"' EXIT

# The pathspec is deliberately plain rather than `:(glob)`-magic. Git's default
# pathspec matching runs wildmatch without WM_PATHNAME, so `*` crosses `/` and
# a pattern like `bin/sd_install*.py` would reach a module in a subdirectory.
# Adding `:(glob)` here would switch on WM_PATHNAME, stop `*` at the separator,
# and silently shrink the measured set -- the exact failure this gate exists to
# prevent. tests/test_installer_coverage_gate.py pins that behaviour so the
# subtlety is checked rather than remembered.
if ! git ls-files -- 'bin/sd_install*.py' >"$tracked_list"; then
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

# Run the report once and reuse it for both the pass/fail gate and the
# statement floor. Reporting twice would let a flaky read pass one and fail the
# other, and it doubles the work for no gain.
if ! "$PYTHON_BIN" -m coverage report --include="$include" --fail-under=100 \
  >"$report_file" 2>&1; then
  cat "$report_file" >&2
  exit 1
fi
cat "$report_file"

statements="$(awk '$1 == "TOTAL" { print $2 }' "$report_file")"
if [ -z "$statements" ]; then
  printf 'error: could not read the statement count from the coverage report.\n' >&2
  exit 1
fi

if [ "$statements" -lt "$MIN_STATEMENTS" ]; then
  printf 'error: installer surface is %s statement(s), below the declared floor of %s.\n' \
    "$statements" "$MIN_STATEMENTS" >&2
  printf 'A 100%% gate over a gutted file certifies less while still reporting green.\n' >&2
  printf 'If the shrink is intended, lower MIN_STATEMENTS in this script in the same pull request.\n' >&2
  exit 1
fi

printf 'diagnostic: installer surface is %s statement(s) (floor %s)\n' \
  "$statements" "$MIN_STATEMENTS" >&2
