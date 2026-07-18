#!/usr/bin/env bash
# Parallel test runner. Shards the unittest suite by module across workers so
# coverage's --parallel-mode writes one data file per shard, which a later
# `coverage combine` merges. Writes unittest-output.log (for the skipped-test
# gate) and exits non-zero if any shard's tests fail.
#
# Env:
#   PYTHON_BIN     interpreter to run (default: python3)
#   TEST_WORKERS   parallel workers (default: online CPUs minus one, min 1)
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

PYTHON_BIN="${PYTHON_BIN:-python3}"
# Shipped helpers invoked through the toolchain resolver during tests must use
# the same interpreter as coverage. Otherwise a consumer fixture without its
# own venv can select a different Homebrew Python whose sitecustomize cannot
# import this run's coverage dependency.
if [ -z "${SD_AI_COMMAND_PACK_PYTHON:-}" ]; then
  case "$PYTHON_BIN" in
    /*) toolchain_python="$PYTHON_BIN" ;;
    */*)
      toolchain_python="$(
        cd -- "$(dirname -- "$PYTHON_BIN")" &&
          printf '%s/%s\n' "$PWD" "$(basename -- "$PYTHON_BIN")"
      )"
      ;;
    *) toolchain_python="$(command -v -- "$PYTHON_BIN")" ;;
  esac
  export SD_AI_COMMAND_PACK_PYTHON="$toolchain_python"
fi

if [ -n "${TEST_WORKERS:-}" ]; then
  case "$TEST_WORKERS" in
    '' | *[!0-9]* | 0)
      printf '%s\n' \
        "error: TEST_WORKERS must be a positive integer (got '$TEST_WORKERS')" >&2
      exit 1
      ;;
  esac
else
  cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '4')"
  case "$cores" in
    '' | *[!0-9]*) cores=4 ;;
  esac
  if [ "$cores" -gt 1 ]; then
    TEST_WORKERS=$((cores - 1))
  else
    TEST_WORKERS=1
  fi
fi

# Absolute paths so installer subprocesses spawned from temp cwds still load the
# coverage config and write their shards where `coverage combine` finds them.
export COVERAGE_PROCESS_START="$REPO_ROOT/.coveragerc"
export COVERAGE_FILE="$REPO_ROOT/.coverage"
export PYTHONPATH="$REPO_ROOT/tests/coverage_sitecustomize${PYTHONPATH:+:$PYTHONPATH}"

# Start clean so combine and the skip gate only see this run's data. Create the
# log up front so the skip gate and final cat always have a file to read, even
# if a shard dies before writing any output.
rm -f .coverage .coverage.*
: > unittest-output.log

# Largest test file first (size approximates runtime) to shorten the tail.
# Skip tests/test_install.py: it is an empty compatibility facade
# (load_tests returns no suite), so `unittest tests.test_install` exits 5.
modules=()
while IFS= read -r path; do
  base="$(basename "$path" .py)"
  if [ "$base" = "test_install" ]; then
    continue
  fi
  modules+=("tests.$base")
done < <(ls -S tests/test_*.py 2>/dev/null)

if [ "${#modules[@]}" -eq 0 ]; then
  printf '%s\n' "error: no test modules found under tests/" >&2
  exit 1
fi

work_dir="$(mktemp -d)" || {
  printf '%s\n' "error: cannot create a temporary directory for test shards" >&2
  exit 1
}
trap 'rm -rf "$work_dir"' EXIT
mod_file="$work_dir/modules"
printf '%s\n' "${modules[@]}" > "$mod_file"

# One `coverage run` per module, up to TEST_WORKERS at a time. Each shard's
# output goes to its own log so parallel writers never interleave. xargs exits
# non-zero (123) if any shard command fails.
run_status=0
xargs -P "$TEST_WORKERS" -I {} bash -c '
  "$1" -m coverage run --parallel-mode -m unittest "$3" > "$2/$3.log" 2>&1
' _ "$PYTHON_BIN" "$work_dir" {} < "$mod_file" || run_status=$?

# Concatenate shard output in a stable order for the skipped-test gate.
for module in "${modules[@]}"; do
  if [ -f "$work_dir/$module.log" ]; then
    cat "$work_dir/$module.log" >> unittest-output.log
  fi
done
cat unittest-output.log

if [ "$run_status" -ne 0 ]; then
  exit 1
fi
