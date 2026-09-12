#!/usr/bin/env bash
# Parallel test runner. Shards the unittest suite by module across workers so
# coverage's --parallel-mode writes one data file per shard, which a later
# `coverage combine` merges. Writes unittest-output.log (for the skipped-test
# gate) and exits non-zero if any shard's tests fail.
#
# Both of those live at the repo root, where `make test` and the CI job read
# them, but they are written there only once the run is over: a run in progress
# writes to a private directory and publishes at the end. An interrupted run
# publishes nothing, so the root keeps the last complete run's results rather
# than a half-written mixture of two. Item 522, and see the two blocks below.
#
# Env:
#   PYTHON_BIN     interpreter to run (default: python3)
#   TEST_WORKERS   parallel workers (default: online CPUs minus one, min 1)
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

PYTHON_BIN="${PYTHON_BIN:-python3}"
case "$PYTHON_BIN" in
  /*) toolchain_python="$PYTHON_BIN" ;;
  */*)
    toolchain_dir="$(cd -- "$(dirname -- "$PYTHON_BIN")" 2>/dev/null && pwd)" ||
      toolchain_dir=""
    toolchain_python="${toolchain_dir:+$toolchain_dir/$(basename -- "$PYTHON_BIN")}"
    ;;
  *) toolchain_python="$(command -v -- "$PYTHON_BIN" 2>/dev/null || :)" ;;
esac
if [ -z "$toolchain_python" ] || [ ! -x "$toolchain_python" ]; then
  printf '%s\n' \
    "error: PYTHON_BIN must resolve to an executable (got '$PYTHON_BIN')" >&2
  exit 1
fi

# Shipped helpers invoked through the toolchain resolver during tests must use
# the same interpreter as coverage. Otherwise a consumer fixture without its
# own venv can select a different Homebrew Python whose sitecustomize cannot
# import this run's coverage dependency.
if [ -z "${SD_AI_COMMAND_PACK_PYTHON:-}" ]; then
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

# Everything this run writes goes to a private directory and is published to the
# repo root only when the run is over. Until item 522 the script opened by
# deleting `.coverage .coverage.*` and truncating unittest-output.log at the
# repo root, so those names were shared, mutable, and written from the first
# second of a run to the last. Two runs in one checkout then destroyed each
# other's data in flight, and the orphan control below is there because a run
# whose parent was killed is exactly how a checkout comes to hold two runs
# without the operator knowing it does. Reproduced before the fix, on this
# script: a live shard was deleted two seconds after a second run started, and
# the surviving orphan appended its own output to the second run's log.
work_dir="$(mktemp -d)" || {
  printf '%s\n' "error: cannot create a temporary directory for test shards" >&2
  exit 1
}
run_log="$work_dir/unittest-output.log"
: > "$run_log"

# Absolute paths so installer subprocesses spawned from temp cwds still load the
# coverage config and write their shards where this run collects them.
export COVERAGE_PROCESS_START="$REPO_ROOT/.coveragerc"
export COVERAGE_FILE="$work_dir/.coverage"
export PYTHONPATH="$REPO_ROOT/tests/coverage_sitecustomize${PYTHONPATH:+:$PYTHONPATH}"

# Git 2.54 can detach automatic maintenance after commits and pushes. The test
# suite creates and removes many short-lived repositories, so a detached repack
# can race either TemporaryDirectory cleanup or a cached fixture copy. Disable
# automatic maintenance for every test subprocess; explicit maintenance tests
# can still override these command-scope values when they invoke Git directly.
export GIT_CONFIG_COUNT=3
export GIT_CONFIG_KEY_0=maintenance.auto
export GIT_CONFIG_VALUE_0=false
export GIT_CONFIG_KEY_1=gc.auto
export GIT_CONFIG_VALUE_1=0
export GIT_CONFIG_KEY_2=receive.autogc
export GIT_CONFIG_VALUE_2=false

# Largest test file first (size approximates runtime) to shorten the tail.
modules=()
while IFS= read -r path; do
  modules+=("tests.$(basename "$path" .py)")
done < <(ls -S tests/test_*.py 2>/dev/null)

if [ "${#modules[@]}" -eq 0 ]; then
  printf '%s\n' "error: no test modules found under tests/" >&2
  rm -rf "$work_dir"
  exit 1
fi

mod_file="$work_dir/modules"
printf '%s\n' "${modules[@]}" > "$mod_file"

# --- orphan control -------------------------------------------------------
#
# A killed parent does not stop this run. The shell is reparented and keeps
# going, and the `coverage run` children outlive it either way: stopping a
# clean run left run-tests.sh alive with two coverage processes still writing.
# So the run has to notice that the process which started it is gone, and it
# has to be able to take its whole shard tree down with it.
#
# `set -m` gives the shard job its own process group, so `kill -- -$shard_pgid`
# reaches xargs and every coverage grandchild at once. That is what makes the
# reaping precise: no pattern kill on the basename `run-tests.sh`, which is
# identical in every worktree on this machine and would take out other
# checkouts' suites.
#
# The watchdog is a plain poll of this shell's parent. It acts only on a
# reparent it can read (`ps` returning a different, non-empty ppid) or on this
# shell being gone outright, so an unreadable `ps` leaves the run alone rather
# than killing it on a guess. A run that was already detached when it started
# (ppid 1) has no launcher to watch and gets no watchdog.
shard_pgid=""
watchdog_pid=""
gate_pid=$$
gate_ppid="$PPID"

reap_shards() {
  if [ -n "$shard_pgid" ]; then
    kill -TERM -- "-$shard_pgid" 2>/dev/null
  fi
}

cleanup() {
  if [ -n "$watchdog_pid" ]; then
    kill -TERM "$watchdog_pid" 2>/dev/null
    watchdog_pid=""
  fi
  reap_shards
  rm -rf "$work_dir"
}

on_signal() {
  # Nothing is published from here: a run that was interrupted has no complete
  # data, and the repo root still holds whatever the last finished run left.
  printf '%s\n' "error: test run interrupted; shard processes terminated." >&2
  cleanup
  exit 143
}

trap 'cleanup' EXIT
trap 'on_signal' INT TERM HUP

watchdog() {
  # Stated rather than relied on: bash resets trapped signals in the subshell a
  # background job runs in, and a watchdog that inherited `cleanup` would delete
  # this run's private directory the moment it was told to stand down.
  trap - EXIT INT TERM HUP
  while :; do
    sleep 2
    if ! kill -0 "$gate_pid" 2>/dev/null; then
      reap_shards
      return 0
    fi
    current_ppid="$(ps -o ppid= -p "$gate_pid" 2>/dev/null | tr -d '[:space:]')"
    [ -n "$current_ppid" ] || continue
    [ "$current_ppid" = "$gate_ppid" ] && continue
    printf '%s\n' \
      "error: the process that started this test run exited; terminating the run and its shards." >&2
    reap_shards
    kill -TERM "$gate_pid" 2>/dev/null
    return 0
  done
}

# One `coverage run` per module, up to TEST_WORKERS at a time. Each shard's
# output goes to its own log so parallel writers never interleave. xargs exits
# non-zero (123) if any shard command fails.
run_status=0
set -m
xargs -P "$TEST_WORKERS" -I {} bash -c '
  "$1" -m coverage run --parallel-mode -m unittest "$3" > "$2/$3.log" 2>&1
' _ "$PYTHON_BIN" "$work_dir" {} < "$mod_file" &
shard_pgid=$!
if [ "$gate_ppid" != "1" ]; then
  watchdog &
  watchdog_pid=$!
fi
wait "$shard_pgid" || run_status=$?
set +m

shard_pgid=""

# Concatenate shard output in a stable order for the skipped-test gate. The
# watchdog stays armed through this: a launcher that dies while the log is being
# assembled still leaves an orphan, and an orphan that reaches the publish below
# writes the shared files this change exists to protect.
for module in "${modules[@]}"; do
  if [ -f "$work_dir/$module.log" ]; then
    cat "$work_dir/$module.log" >> "$run_log"
  fi
done

# Publish, and stand the watchdog down first. Everything above is interruptible
# without consequence; from here on an interruption would leave the repo root
# holding half of one run and half of another, which is worse than an orphan
# finishing a publish of data that is already complete and its own.
if [ -n "$watchdog_pid" ]; then
  kill -TERM "$watchdog_pid" 2>/dev/null
  wait "$watchdog_pid" 2>/dev/null
  watchdog_pid=""
fi

# The run is over, so the repo root can now carry its results: the skipped-test
# gate reads unittest-output.log there, and `coverage combine` reads
# `.coverage.*` there, in both `make test` and CI. Clearing the old data happens
# here rather than at startup so the destructive step lands when this run's data
# is complete instead of while another run's data is being written.
#
# Every step is checked. A publish that half-failed and then reported the tests'
# own success would hand the next gate a mixed shard set or a stale log with a
# zero exit, which is the failure mode this script is being fixed for.
publish_status=0
rm -f "$REPO_ROOT/.coverage" "$REPO_ROOT"/.coverage.* || publish_status=1
for shard in "$work_dir"/.coverage.*; do
  [ -e "$shard" ] || continue
  mv -f "$shard" "$REPO_ROOT/" || publish_status=1
done
cat "$run_log" > "$REPO_ROOT/unittest-output.log" || publish_status=1
cat "$REPO_ROOT/unittest-output.log"

if [ "$publish_status" -ne 0 ]; then
  printf '%s\n' \
    "error: could not publish this run's results to $REPO_ROOT; the files there are not this run's." >&2
  exit 1
fi

if [ "$run_status" -ne 0 ]; then
  exit 1
fi
