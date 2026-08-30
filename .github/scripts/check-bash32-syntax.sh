#!/usr/bin/env bash
# Reject tracked shell that macOS bash 3.2 rejects, before the push.
#
# The local gates parse shell with whichever bash sits on PATH. On a machine
# carrying Homebrew bash 5 that hides constructs only bash 3.2 rejects — an
# apostrophe in a comment inside a "$( ... )" substitution, for one — and the
# error, when it surfaces, quotes a line number at the end of the file rather
# than the defect.
#
# This runs in two places: a local "make lint", and the bash32 CI job, which
# builds bash 3.2 from source (no Linux distro packages it) and invokes this
# script with STRICT=1 so a missing interpreter fails instead of skipping.
#
# Scripts are enumerated from the tracked set at run time (every "*.sh" plus
# any tracked git hook carrying a shell shebang), never from a list kept here,
# so a script added tomorrow is covered without editing this gate.
#
# Interpreter resolution: candidates come from SD_AI_COMMAND_PACK_BASH32 when
# that variable is set (space-separated paths), otherwise from the probe list
# below. Every candidate is version-probed, so only a real bash 3.2 is used.
# A platform with no bash 3.2 — Linux carries none — prints a visible skip and
# exits 0, or fails when STRICT=1 demands the lane.
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

STRICT="${STRICT:-0}"

candidate_paths() {
  if [ -n "${SD_AI_COMMAND_PACK_BASH32+x}" ]; then
    printf '%s\n' "${SD_AI_COMMAND_PACK_BASH32}"
    return 0
  fi
  printf '%s\n' "/bin/bash /usr/bin/bash /usr/local/bin/bash /opt/homebrew/bin/bash $(command -v bash 2>/dev/null)"
}

is_bash32() {
  local candidate="$1"
  local version=""

  [ -x "$candidate" ] || return 1
  version="$("$candidate" --version 2>/dev/null | head -n 1)"
  case "$version" in
    *"version 3.2"*) return 0 ;;
    *) return 1 ;;
  esac
}

resolve_bash32() {
  local candidate=""

  # Word splitting is the point: the candidate list is space-separated.
  # shellcheck disable=SC2013,SC2046
  for candidate in $(candidate_paths); do
    if is_bash32 "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

is_shell_file() {
  local path="$1"
  local first_line=""

  case "$path" in
    *.sh) return 0 ;;
  esac
  # A tracked git hook has no suffix, so its shebang decides. Read the line
  # into a variable rather than piping it: `set -o pipefail` would otherwise
  # report a reader that exits early as a pipeline failure.
  first_line="$(head -n 1 -- "$path" 2>/dev/null)"
  case "$first_line" in
    '#!'*sh | '#!'*sh[[:space:]]*) return 0 ;;
    *) return 1 ;;
  esac
}

# Enumerate first and check the status. Reading `git ls-files` through a
# process substitution would discard its exit status, so a git that is missing
# or a checkout that is not a work tree would feed the loop nothing, land on
# `checked -eq 0`, and exit 0 — a silent pass, which is the same defect this
# gate exists to catch.
tracked_list="$(mktemp)"
trap 'rm -f "$tracked_list"' EXIT

if ! git ls-files -z -- '*.sh' >"$tracked_list"; then
  printf '%s\n' \
    "error: git ls-files failed; cannot enumerate tracked shell scripts for the bash 3.2 gate." >&2
  exit 1
fi

BASH32="$(resolve_bash32)"

if [ -z "$BASH32" ]; then
  if [ "$STRICT" = "1" ]; then
    printf '%s\n' \
      "error: no bash 3.2 interpreter found and STRICT=1; the bash 3.2 syntax lane is required." >&2
    exit 1
  fi
  printf '%s\n' \
    "warning: no bash 3.2 interpreter found; skipping bash 3.2 syntax checks here. The bash32 CI job builds bash 3.2 and runs this gate under STRICT=1, so the lane is enforced there even though this run skipped it. Set STRICT=1 to make the absence an error locally too."
  exit 0
fi

checked=0
failed=0

while IFS= read -r -d '' path; do
  if ! is_shell_file "$path"; then
    continue
  fi
  checked=$((checked + 1))
  if ! "$BASH32" -n "$path"; then
    printf 'error: %s is rejected by bash 3.2 at %s\n' "$path" "$BASH32" >&2
    failed=$((failed + 1))
  fi
done <"$tracked_list"

if [ "$checked" -eq 0 ]; then
  printf 'No tracked shell scripts found.\n'
  exit 0
fi

if [ "$failed" -ne 0 ]; then
  printf 'error: %s of %s tracked shell scripts rejected by bash 3.2.\n' \
    "$failed" "$checked" >&2
  exit 1
fi

printf 'bash 3.2 syntax gate: %s tracked shell scripts accepted by %s.\n' \
  "$checked" "$BASH32"
