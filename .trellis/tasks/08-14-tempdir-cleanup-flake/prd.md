# Tolerate temp-dir teardown races in the install test helpers

## Goal

Stop `unittest` teardown from failing with `OSError: [Errno 39] Directory not
empty` when a test's temporary tree contains a git repository. This ports the
fix already shipped in `se-ai-command-pack` PR #225 (commit `7bbba64`).

## Background

The install test helpers create a temporary directory and immediately run
`git init` inside it:

```python
tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
self.addCleanup(tempdir.cleanup)
root = Path(tempdir.name)
self.run_git(root, "init")
```

`tests/install_test_support.py:145` (`make_repo`) and `:160`
(`make_git_repo_without_trellis`). The other two helper sites host git
repositories the same way: `:908` builds a work tree plus a bare remote
(`git init --bare` at `:920`), and `:1055` copies a cached template repository
in and repoints its origin. All four therefore carry the precondition.

Git's automatic garbage collection runs as a **separate background process**.
When it fires against one of those throwaway repositories, it can write under
the tree after `shutil.rmtree` has scanned a directory but before it calls
`rmdir` on it. The directory is empty at scan time and non-empty at removal
time, so cleanup raises `Errno 39` and the test errors in teardown — after the
test body itself has already passed.

`tempfile.TemporaryDirectory(ignore_cleanup_errors=True)` swallows exactly this
error class, leaving the stray files for the OS to reap.

## Evidence this applies here

Measured on `origin/main` at `a129437c`:

| Fact | Value |
|---|---|
| `TemporaryDirectory(` call sites under `tests/` | 216 |
| …of those, in the shared helper `install_test_support.py` | 4 |
| Files using `ignore_cleanup_errors` | 0 |
| Helper call sites hosting a git repository | all 4 — `:145`, `:160`, `:908`, `:1055` |
| CI Python matrix | 3.10 and 3.13 (`requires-python = ">=3.10"`) |

**No occurrence of this flake has been observed in this repository.** A search
for `Errno 39` / `Directory not empty` across `tests/` and `.trellis/` returns
nothing. This is a latent hazard with every precondition present, not an active
failure. In `se-ai-command-pack` the same construction failed roughly once per
several hundred CI job runs before it was fixed.

## How this repository differs from the origin of the fix

`se-ai-command-pack` funnels every temporary tree through **one** base class,
`TempDirTestCase`, so its fix was a single-line change plus tests.

This repository has no such funnel: 216 independent call sites, only 4 of them
shared. A verbatim port is therefore not available, and the design step must
choose a scope rather than assume one. That choice is deliberately left open
here — see the design task below.

## Requirements

- Teardown must not fail when a background git process writes into a temporary
  tree during cleanup.
- The fix must work on both Python 3.10/3.11 and 3.12+. `shutil.rmtree`'s error
  handler changed shape between them: 3.12 introduced `onexc`, which receives
  the exception instance, while 3.10/3.11 pass `onerror` a
  `(type, value, traceback)` triple. Anything that installs a handler must
  cover both.
- No test may have its assertions weakened, skipped, or made conditional to
  achieve this. The failure is in teardown, not in any test body.
- Errors unrelated to the race must not be silently swallowed. Whatever is
  suppressed must be scoped to cleanup of the throwaway tree.

## Acceptance Criteria

- [ ] Temporary trees created by the shared helpers in
      `tests/install_test_support.py` tolerate a concurrent writer during
      cleanup.
- [ ] The chosen scope is stated explicitly in `design.md` — shared helpers
      only, or all 216 call sites — with the reasoning for excluding whatever
      is excluded, and the residual risk of the excluded set named.
- [ ] Unit tests drive the cleanup path directly on **both** handler shapes
      (`onexc` for 3.12+, `onerror` for 3.10/3.11) with a synthetic `Errno 39`,
      and assert cleanup returns rather than raises.
- [ ] Full suite green on the existing CI matrix (3.10 and 3.13), with no test
      newly skipped.

### Explicitly not an acceptance criterion

Reproducing the real race. It is a timing window against a separate process and
cannot be staged reliably: holding a file open does **not** block `unlink` on
POSIX — the directory entry is removed and the inode persists until the last
descriptor closes — so the obvious staging attempt does not reproduce anything.

`se-ai-command-pack` wrote this reproduction into its acceptance criteria,
could not meet it, and closed the task with the gap recorded (see that repo's
`.trellis/tasks/archive/2026-08/08-14-tempdir-cleanup-flake/prd.md`). Do not
repeat that: confidence here rests on the mechanism plus handler-level tests,
and this PRD says so up front rather than discovering it at close-out.

## Constraints

- `tests/install_test_support.py` is shared by ~44 test modules. A change to
  the helper signature or return type ripples widely; prefer a change that is
  invisible to callers.
- This task is planning-only as filed. Implementation needs the usual review
  gate, and the scope decision above should be settled in `design.md` first.

## Notes

- Origin of the fix: `se-ai-command-pack` PR #225, commit `7bbba64`, plus its
  regression tests in `tests/test_install_test_support.py`.
- Filed from a fleet sweep after that repo's flake fix landed; the sweep found
  this repository to be the only other one in the fleet with all the
  preconditions present.
