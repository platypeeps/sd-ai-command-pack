#!/bin/sh
# A fake of the system checkout's leak-guard.sh for the dashboard's tests
# (sd:6044): `scan` alone. It prints the number of each stdin line that a
# pattern in <config>/privacy-patterns (or $LEAK_GUARD_PATTERNS) matches and
# exits 1, exits 0 when none does, and 3 when there is no pattern to apply.
set -eu
[ "${1:-}" = scan ] || { echo "leak-guard: the fake runs only scan" >&2; exit 2; }
config="${SYSTEM_TOOLS_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/system}"
file="${LEAK_GUARD_PATTERNS:-$config/privacy-patterns}"
work="$(mktemp -d "${TMPDIR:-/tmp}/leak-guard.XXXXXX")"
trap 'rm -rf "$work"' EXIT
[ -f "$file" ] || exit 3
grep -Ev '^[[:space:]]*(#|$)' "$file" > "$work/patterns" || true
[ -s "$work/patterns" ] || exit 3
cat > "$work/text"
code=0
grep -a -n -E -f "$work/patterns" "$work/text" > "$work/matches" || code=$?
case "$code" in
  0) cut -d: -f1 "$work/matches"; exit 1 ;;
  1) exit 0 ;;
  *) exit 2 ;;
esac
