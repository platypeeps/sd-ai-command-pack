# Isolate concurrent agent sessions via git worktrees

## Goal

Two agent sessions working the same repository must not corrupt each other's
working-tree state or verification results; the default for a second session
is an isolated git worktree, and the shared expensive gate is exclusive.

## Problem

On 2026-08-09 two Claude sessions worked the same checkout concurrently while
executing 08-09-thin-machine-installer. Observed collisions, all real:

- Working-tree overwrites: one session's in-flight `installer/machinescope.py`
  and `tests/test_machine_installer.py` were rewritten by the other between
  validation and commit, invalidating pinned content digests and causing four
  spurious test failures from a partially-written module import.
- Coverage-shard clobbering: `run-tests.sh` begins with
  `rm -f .coverage .coverage.*`, so two concurrent `make test` runs delete each
  other's shards. Observed 31+ competing `coverage run` processes and bogus
  results (sub-floor 44%/70%/72% coverage, "No data to report") that cleared
  on uncontended reruns.
- Ownership opacity: `task.py current` is session-scoped, so neither session
  could see that the other owned the active task; both dispatched implement
  agents against the same step.

Each collision cost a diagnosis loop and forced content re-verification before
any commit could proceed safely.

## Requirements

1. Second-session isolation: session bootstrap (sd-start or equivalent)
   detects an already-active session in the checkout (session lockfile, recent
   mtime activity, or running gate processes) and creates/offers a git
   worktree for the new session instead of sharing the tree.
2. Exclusive gate: `make test` refuses or queues when another run is active in
   the same tree (lockfile or process guard) instead of silently corrupting
   coverage shards.
3. Visibility: `sd-status` reports evidence of a second active session in the
   same checkout.
4. Documentation: workflow guide states the convention — single writer per
   working tree, worktree per session, gates are exclusive.

## Acceptance Criteria

- [ ] Starting a second session against a busy checkout lands it in a distinct
      worktree, or warns and requires explicit opt-in to share.
- [ ] Concurrent `make test` in one tree is refused or queued; a test proves
      the guard (second invocation blocks while the first holds the lock).
- [ ] Stale locks cannot brick the gate: age-based takeover or pid liveness
      check, with a test.
- [ ] `sd-status` shows second-session evidence when present.
- [ ] Workflow docs updated; `make test` and review preflight green.

## Constraints

- Must not break single-session flows or CI (CI runs are already isolated).
- Worktree creation must respect the existing `.trellis/worktrees/` gitignore
  convention or place worktrees outside the repository.
