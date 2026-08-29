---
title: Convert review_preflight installs to in-process twin
status: done
created: 2026-08-02
---
# PRD: Convert review_preflight installs to the in-process twin

## Problem

`tests/test_review_preflight.py` is the slowest test module (~70s under
coverage, ~2x the next), and because `run-tests.sh` shards by module it bounds
the whole CI test step's tail. The cost is not CPU or coverage tracing (removing
coverage changed wall-clock by noise); it is subprocess spawning. The module
has 54 `self.run_install(root)` call sites (two inside `subTest` loops, so ~56
runtime invocations), and each call spawns a full `python install.py`
subprocess with coverage startup. The in-process twin
`run_install_inproc` exists precisely for install-then-inspect callers but is
used 0 times in this module.

Worker oversubscription was already tried and rejected (PR #312): it gave ~6%
on the 4-core CI runner because the runner has no spare cores. Reducing total
work is the only lever that helps on a fixed core count.

## Goal

Cut `test_review_preflight` wall-clock by converting its eligible
`run_install` (subprocess) calls to `run_install_inproc`, without changing any
test's meaning and without regressing the installer 100% coverage gate.

## Scope

In scope:
- `tests/test_review_preflight.py` only. Per-call classification and conversion
  of `run_install` -> `run_install_inproc` where the call is a fixture bootstrap
  (install then inspect filesystem / return code).

Out of scope:
- Other modules (`test_install_audit`, `test_full_check`, `test_review_scope`,
  etc.) -- separate follow-ups, measured after this one lands.
- Any change to `run_install`, `run_install_inproc`, `install.py`, or
  `run-tests.sh`.
- Larger CI runners (priced and rejected: paid even for public repos).

## Constraints

- C1. No assertion or behavioral change. A converted test must assert exactly
  what it asserted before and pass identically.
- C2. Keep `run_install` (subprocess) for any call that depends on process
  semantics: argv/CLI parsing, `os.environ`/PATH isolation, `SystemExit` as a
  process exit status, or the symlink-exec entry point. The twin's docstring
  enumerates these.
- C3. The installer coverage gate (`coverage report --include="install.py,
  installer/*" --fail-under=100`) must still pass. The subprocess-only entry
  lines (`install.py:873-874` `__main__`, `:703/:705` bad-flag `SystemExit`) are
  already owned by dedicated tests independent of review_preflight
  (`test_install_core.py:2358` `--backup`, `:2690` `--skip-trellis-init`,
  `:2204-2219` symlink entry), so full conversion should not drop the gate. If
  it does, the recovery
  is to add a focused installer-entry test, NOT to un-convert review_preflight
  fixture calls.
- C4. Calls passing `extra_env=` cannot swap directly (the twin has no such
  param). Confirmed count in this module: 0. If any exist at implementation
  time, they stay on `run_install`.
- C5. In-process `install.main` must not leak global state (cwd, os.environ,
  sys.argv) across the converted tests. A test module runs in one process, so
  same-module leakage between the in-proc installs is the real risk (cross-shard
  is impossible). Prove non-leakage with an explicit before/after snapshot of
  `Path.cwd()` / `os.environ` / `sys.argv` around one in-proc install; a passing
  sharded run alone is NOT proof. If any state leaks, that call stays subprocess
  or the leak is contained.

## Acceptance criteria

- AC1. Eligible `run_install(root)` calls in `test_review_preflight.py` are
  converted to `run_install_inproc(root)`. Expected post-edit static counts:
  0 `run_install`, 54 `run_install_inproc` (all sites eligible; none passes
  `extra_env=` or asserts installer process semantics). Any site kept subprocess
  is a genuine exception discovered at edit time, with a one-line reason.
- AC2. `python -m unittest tests.test_review_preflight` passes with the same
  test count as before (0 new failures, 0 new skips).
- AC3. Full suite via `run-tests.sh` passes, `coverage combine` succeeds, and
  the installer coverage gate reports 100% (C3).
- AC4. Measured `test_review_preflight` wall-clock drops materially versus the
  ~70s baseline, where both baseline and post-conversion are timed under the
  FULL CI environment (`COVERAGE_PROCESS_START`, `COVERAGE_FILE`,
  `PYTHONPATH=tests/coverage_sitecustomize`, `SD_AI_COMMAND_PACK_PYTHON`, and
  the three `GIT_CONFIG_*` gc-off vars — the incomplete env spuriously fails a
  scope-advisory test) so subprocess child coverage is active in the baseline.
  Target: >=30% module wall-clock reduction; the concrete before/after seconds
  are recorded in the commit body.
- AC5. `make check` exits 0.

## Outcome: ABANDONED — hypothesis falsified (2026-08-02)

Implemented the full conversion (all 54 sites -> `run_install_inproc`, isolation
proven: cwd/os.environ/sys.argv unchanged, 66 tests OK) and measured before/after
under the full CI env:

| env | pre | post | delta |
|-----|-----|------|-------|
| coverage (CI-relevant) | 92.2s | 87.5s | -5.1% |
| plain (no coverage)    | 79.8s | 77.9s | -2.4% |

AC4 (>=30% reduction) FAILS. Root cause, measured: subprocess spawn is only
~35ms/call (plain delta 1.9s / 54); each install's real cost is its copytree +
git I/O, identical in-proc or subprocess. The module also makes 44 node
preflight `subprocess.run` calls (the unit under test, unconvertible). Neither
dominant cost is addressed by in-proc conversion. Same falsification pattern as
PR #312 (worker oversubscription, ~6%).

Conversion reverted; nothing shipped. Real levers for a future task: a
shared/cached install fixture to cut the copytree I/O x54, or reducing the 44
node-preflight spawns.
