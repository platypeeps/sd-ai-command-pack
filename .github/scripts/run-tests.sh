#!/usr/bin/env bash
# Parallel test runner. Shards the unittest suite across workers -- one shard
# per module, except the few modules named in SPLIT_MODULES, which are split by
# test id -- so coverage's --parallel-mode writes one data file per shard, which
# a later `coverage combine` merges. Writes unittest-output.log (for the skipped-test
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
#   TEST_WORKERS   workers (default: all CPUs in CI; CPUs minus one locally, min 1)
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
  [ "$cores" -ge 1 ] || cores=1
  if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
    TEST_WORKERS="$cores"
  elif [ "$cores" -gt 1 ]; then
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
#
# SD_COVERAGE_PROCESS_START, not coverage's own COVERAGE_PROCESS_START: the
# latter makes coverage's `.pth` file start measuring in every Python process
# that inherits it, and nearly all of the suite's Python children (the `git` and
# `gh` shims tests put on PATH, `sd-review` under `sd-ship`) run nothing in
# `[run] include`. tests/coverage_sitecustomize starts coverage in a child only
# when that child executes a file the include patterns name; the docstring there
# has the measurements. The installer gate at 100% is what shows nothing is lost.
export SD_COVERAGE_PROCESS_START="$REPO_ROOT/.coveragerc"
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

# --- changed-files fast path (sd:10 criterion 16) -------------------------
#
# Set, even to nothing, by `make check CHANGED="<paths>"` and by nothing else.
# Unset, which is every CI run and every plain `make check`, the whole suite
# runs and nothing below changes a byte of it. select-tests.py says which
# modules the paths need, or `full`; its docstring has the rules. Any doubt
# runs the whole suite: a CI runner -- `CI` or `GITHUB_ACTIONS` set to a
# non-empty value, since a runner is free to export `CI=1`, while an empty
# `CI=` is not a runner and does not stop the fast path -- a list that holds
# no path, a selector that fails or prints nothing, or a selection that
# matches no module here. A run that did narrow writes
# FAST_PATH_MARK as the first line of the log, and `make test` reads that line
# to skip `coverage combine` and the installer gate, which a partial run
# cannot meet.
FAST_PATH_MARK="test selection: changed files"
if [ -n "${TEST_CHANGED_FILES+set}" ]; then
  if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
    printf '%s\n' "warning: TEST_CHANGED_FILES is ignored under CI; running the full suite" >&2
  else
    set -f
    # shellcheck disable=SC2086 # one path per word, and a path here has no blanks
    selection="$(env -u SD_COVERAGE_PROCESS_START "$PYTHON_BIN" \
      "$REPO_ROOT/.github/scripts/select-tests.py" -- $TEST_CHANGED_FILES)" || selection=""
    set +f
    selected=()
    # The `full` comparison is defence in depth, and nothing rests on it
    # today: every name below is `tests.` and a file's stem, so the word
    # `full` is a whole line no name can equal, the selection stays empty,
    # and the fallback below runs the whole suite anyway. It is here so that
    # a selector sentinel that did one day collide with a module name would
    # narrow nothing.
    #
    # A name matches a whole line of the selection, never a substring, and
    # the match is made in this shell rather than through `printf | grep`.
    # Whole line: a selection naming `tests.test_alphabet`, which this tree
    # does not hold, must match nothing and fall to the full run below; a
    # substring match would narrow to `tests.test_alpha` instead and skip
    # the coverage gates. In this shell: `set -o pipefail` is in force, so a
    # `grep -q` that exited on its first match while `printf` was still
    # writing a selection longer than a pipe buffer made the pipeline 141,
    # which read as "not selected". The module was dropped, and the run
    # reported a count the selector did not give. A real selection is a few
    # kilobytes and did not reach it; a megabyte did, every time.
    newline=$'\n'
    lines="$newline$selection$newline"
    if [ -n "$selection" ] && [ "$selection" != "full" ]; then
      for name in "${modules[@]}"; do
        case "$lines" in
          *"$newline$name$newline"*) selected+=("$name") ;;
        esac
      done
    fi
    if [ "${#selected[@]}" -eq 0 ]; then
      printf '%s\n' "changed-files fast path: running the full suite" >&2
    else
      printf '%s\n' "$FAST_PATH_MARK, ${#selected[@]} of ${#modules[@]} modules" > "$run_log"
      printf '%s\n' "changed-files fast path: ${#selected[@]} of ${#modules[@]} modules; not the full suite" >&2
      modules=("${selected[@]}")
    fi
  fi
fi

# Modules split below module level, by test id, into up to TEST_WORKERS shards
# each. Sharding by module lets the slowest module set the wall clock on its
# own: on CI (#907, three workers) tests.test_sd_ship ran 1155 s of a 1173 s
# step while the other workers sat idle. Every test in these modules builds its
# own fixtures in setUp, which is what makes a split by id safe: a split runs
# a class fixture once per shard holding one of its tests, not once.
#
# That is checked, not assumed. Before a module here is split, every test class
# it loads is checked for a setUpClass or tearDownClass of its own or from a
# base outside unittest, and the module itself and every module those classes
# come from for setUpModule, tearDownModule or load_tests, which a split by id
# would bypass. A module that
# has any of them stops the run with the names; it leaves this list or loses
# the fixture. The check runs on whatever this list names, so a module added
# later is held to it too.
#
# A name here that matches no file is skipped rather than refused, so a rename
# costs time and never a test: the renamed module still runs, whole.
SPLIT_MODULES="tests.test_sd_ship tests.test_sd_ship_dispositions tests.test_sd_ship_disposition_guards"

# The ids a module holds, one per line, loaded the way `python -m unittest
# <module>` loads them. Fails, printing nothing, if the module does not import
# or holds no tests; the caller then runs it whole, and the whole-module run
# reports whatever went wrong. Exits 3, naming them on stderr, if the module
# has a fixture that must run once.
module_test_ids() {
  env -u SD_COVERAGE_PROCESS_START "$PYTHON_BIN" -c '
import sys
import unittest


def walk(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from walk(test)
        else:
            yield test


tests = list(walk(unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])))
if not tests or any(type(test).__module__.startswith("unittest.") for test in tests):
    sys.exit(1)
fixtures = set()
for cls in {type(test) for test in tests}:
    for name in ("setUpClass", "tearDownClass"):
        defined = next(klass for klass in cls.__mro__ if name in vars(klass))
        if defined.__module__.split(".")[0] != "unittest":
            fixtures.add(f"{defined.__module__}.{defined.__qualname__}.{name}")
for module_name in {type(test).__module__ for test in tests} | {sys.argv[1]}:
    module = sys.modules.get(module_name)
    for name in ("setUpModule", "tearDownModule", "load_tests"):
        if hasattr(module, name):
            fixtures.add(f"{module_name}.{name}")
if fixtures:
    print("\n".join(sorted(fixtures)), file=sys.stderr)
    sys.exit(3)
print("\n".join(test.id() for test in tests))
' "$1"
}

# Each shard is a name and a `<name>.ids` file holding the unittest arguments
# it runs, one per line: the module name for a whole module, test ids for a
# split one. Split shards are scheduled first, because they are the long ones.
split_shards=()
whole_shards=()
for name in "${modules[@]}"; do
  split=0
  case " $SPLIT_MODULES " in
    *" $name "*)
      fixtures_file="$work_dir/$name.fixtures"
      ids="$(module_test_ids "$name" 2>"$fixtures_file")"
      list_status=$?
      if [ "$list_status" -eq 3 ]; then
        printf '%s\n' \
          "error: $name is in SPLIT_MODULES, but a split by test id would run these once per shard:" >&2
        sed 's/^/  /' "$fixtures_file" >&2
        printf '%s\n' \
          "Take $name out of SPLIT_MODULES in .github/scripts/run-tests.sh, or move the fixture into setUp." >&2
        rm -rf "$work_dir"
        exit 1
      fi
      if [ "$list_status" -eq 0 ] && [ -n "$ids" ]; then
        split=1
      else
        cat "$fixtures_file" >&2
        printf '%s\n' "warning: could not list the tests in $name; running it as one shard" >&2
      fi
      ;;
  esac
  if [ "$split" -eq 0 ]; then
    printf '%s\n' "$name" > "$work_dir/$name.ids"
    whole_shards+=("$name")
    continue
  fi
  count="$(printf '%s\n' "$ids" | wc -l | tr -d ' ')"
  parts="$TEST_WORKERS"
  [ "$parts" -le "$count" ] || parts="$count"
  part=1
  while [ "$part" -le "$parts" ]; do
    # Round robin over the ids in load order: the part holding the kth id is
    # k mod parts, so every id lands in exactly one part.
    printf '%s\n' "$ids" | awk -v parts="$parts" -v part="$part" \
      '(NR - 1) % parts == part - 1' > "$work_dir/$name.part${part}of${parts}.ids"
    split_shards+=("$name.part${part}of${parts}")
    part=$((part + 1))
  done
done
shards=("${split_shards[@]+"${split_shards[@]}"}" "${whole_shards[@]+"${whole_shards[@]}"}")

shard_file="$work_dir/shards"
printf '%s\n' "${shards[@]}" > "$shard_file"

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

# sd:1407. The footer that matches the header below: the same pid and head,
# with the exit, so a reader can tell which run a log line belongs to and
# whether it saw their edit. `cleanup` runs on every exit and once more after a
# signal, and the footer is printed once.
run_head=""
footer_printed=""
run_footer() {
  if [ -n "$run_head" ] && [ -z "$footer_printed" ]; then
    footer_printed=1
    printf 'run-tests: end head=%s pid=%s exit=%s at=%s\n' \
      "$run_head" "$$" "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
  fi
}

cleanup() {
  local status=$?
  [ -z "${1:-}" ] || status=$1
  if [ -n "$watchdog_pid" ]; then
    kill -TERM "$watchdog_pid" 2>/dev/null
    watchdog_pid=""
  fi
  reap_shards
  rm -rf "$work_dir"
  release_gate_slot
  run_footer "$status"
}

on_signal() {
  # Nothing is published from here: a run that was interrupted has no complete
  # data, and the repo root still holds whatever the last finished run left.
  printf '%s\n' "error: test run interrupted; shard processes terminated." >&2
  cleanup 143
  exit 143
}

trap 'cleanup' EXIT
trap 'on_signal' INT TERM HUP

# sd:1541. At most SD_GATE_SLOTS local runs at once on this machine. On
# 2026-09-25 several gates started together, the load average reached 157, and
# tests with a fixed bound failed three of them. `make test` sets the cap; unset
# or 0 means none, and CI never waits. A slot is a directory, taken with an
# atomic `mkdir` and holding the runner's pid, so a slot whose holder is gone
# is taken over. A holder exports SD_GATE_SLOTS=0: the runs its tests start
# inside it must not wait on the slot their own parent holds.
gate_slot=""
release_gate_slot() {
  if [ -n "$gate_slot" ]; then
    rm -rf -- "$gate_slot"
    gate_slot=""
  fi
}
acquire_gate_slot() {
  local slots="${SD_GATE_SLOTS:-0}" dir i slot holder announced=""
  case "$slots" in
    '' | *[!0-9]*)
      printf '%s\n' "error: SD_GATE_SLOTS must be a non-negative integer (got '$slots')" >&2
      exit 1
      ;;
  esac
  if [ "$slots" -eq 0 ] || [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
    return 0
  fi
  dir="${SD_GATE_SLOTS_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/sd/gate-slots}"
  if ! mkdir -p -- "$dir" 2>/dev/null; then
    printf '%s\n' "warning: cannot create $dir; running without the gate cap" >&2
    return 0
  fi
  while :; do
    for ((i = 1; i <= slots; i++)); do
      slot="$dir/slot.$i"
      if ! mkdir -- "$slot" 2>/dev/null; then
        holder="$(cat -- "$slot/pid" 2>/dev/null)"
        # A holder that died before writing its pid leaves an empty slot; a
        # minute is far longer than the write takes.
        if { [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; } ||
          { [ -z "$holder" ] && [ -n "$(find "$slot" -maxdepth 0 -mmin +1 2>/dev/null)" ]; }; then
          rm -rf -- "$slot"
          mkdir -- "$slot" 2>/dev/null || continue
        else
          continue
        fi
      fi
      printf '%s\n' "$$" >"$slot/pid"
      gate_slot="$slot"
      export SD_GATE_SLOTS=0
      return 0
    done
    if [ -z "$announced" ]; then
      printf '%s\n' "waiting for a gate slot: $slots of $slots in use under $dir" >&2
      announced=1
    fi
    sleep "${SD_GATE_SLOT_POLL:-5}"
  done
}
acquire_gate_slot

# sd:1407. The tree this run imports from, named before the first test: a log
# from a run that started before an edit reads as current otherwise, since a
# traceback quotes the file as it is now, not as the run loaded it.
run_head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" || run_head=""
if [ -n "$run_head" ]; then
  run_dirty="$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d '[:space:]')"
else
  run_head="unknown"
  run_dirty="unknown"
fi
# On stderr: stdout is the run log, byte for byte (unittest-output.log).
printf 'run-tests: start head=%s dirty=%s pid=%s at=%s\n' \
  "$run_head" "$run_dirty" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2

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

# One `coverage run` per shard, up to TEST_WORKERS at a time. Each shard's
# output goes to its own log so parallel writers never interleave. xargs exits
# non-zero (123) if any shard command fails. The ids are read from a file, not
# passed through xargs, because BSD xargs caps a `-I` replacement at 255 bytes.
# An empty ids file is refused: `python -m unittest` with no names discovers and
# runs the whole tree.
printf 'test runner: workers=%s shards=%s\n' "$TEST_WORKERS" "${#shards[@]}" >> "$run_log" || exit 1
run_status=0
set -m
xargs -P "$TEST_WORKERS" -I {} bash -c '
  set -f
  ids="$(cat "$2/$3.ids")" && [ -n "$ids" ] || {
    printf "%s\n" "error: shard $3 has no test names" > "$2/$3.log"
    exit 1
  }
  # Unquoted on purpose: one name per line, and a unittest name has no blanks.
  started=$SECONDS
  "$1" -m coverage run --parallel-mode -m unittest $ids > "$2/$3.log" 2>&1
  status=$?
  printf "\nshard %s: %ss exit=%s\n" "$3" "$((SECONDS - started))" "$status" >> "$2/$3.log" || exit 1
  exit "$status"
' _ "$PYTHON_BIN" "$work_dir" {} < "$shard_file" &
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
#
# The append is checked because this log is evidence, not a convenience: `make
# test` decides whether the suite skipped anything by reading it, so a write
# that failed half way -- a full temporary filesystem is the ordinary way --
# would publish a log missing whatever those shards reported and pass the skip
# gate by omission. A run that cannot assemble its own log publishes nothing and
# says why, leaving the root on the last complete run.
assembly_status=0
for shard in "${shards[@]}"; do
  if [ -f "$work_dir/$shard.log" ]; then
    cat "$work_dir/$shard.log" >> "$run_log" || assembly_status=1
  fi
done

if [ "$assembly_status" -ne 0 ]; then
  printf '%s\n' \
    "error: could not assemble this run's log under $work_dir; nothing was published." >&2
  exit 1
fi

# Publish, and stand the watchdog down first. Everything above is interruptible
# without consequence; from here on an interruption would leave the repo root
# holding half of one run and half of another, which is worse than an orphan
# finishing a publish of data that is already complete and its own.
if [ -n "$watchdog_pid" ]; then
  kill -TERM "$watchdog_pid" 2>/dev/null
  wait "$watchdog_pid" 2>/dev/null
  watchdog_pid=""
fi

# Standing the watchdog down is not on its own enough to make the publish
# uninterruptible: the INT/TERM/HUP trap installed above would still fire
# between the `rm` and the `mv`, and `on_signal` would exit with the old data
# deleted and the new data never moved in. Reproduced, with the window held
# open: `exit=143 terms=13 blocks=2 shards=0` -- no coverage at the repo root
# at all, under a log describing the run before it. So the publish runs with
# those three signals ignored. SIGKILL cannot be masked and is not claimed to
# be; what is claimed is that an operator's Ctrl-C or `kill` cannot cut the
# publish in half.
trap '' INT TERM HUP

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
