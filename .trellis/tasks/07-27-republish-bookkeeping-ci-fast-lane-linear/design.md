# Design: Linear replacement publication

## Boundary

The recovery changes publication history and Trellis lifecycle artifacts, not
the fast-lane behavior. PR #270 at `3d1a82779e8d4fefe4329e5f4d6b9327388b28b4`
is the content reference. `origin/main` is the replacement branch base.

## History Shape

1. Create `codex/republish-bookkeeping-ci-fast-lane-linear` from the current
   `origin/main`.
2. Carry this planning task onto that branch and activate both it and the
   original `07-24-add-bookkeeping-only-ci-fast-lane` task.
3. Replay the reviewed functional file contents from `3d1a827` as ordinary
   single-parent work commits. Do not replay PR #270's archive, journal,
   restoration, or merge commits.
4. Capture the finalization base after the last work commit.
5. Run the canonical pre-archive gate for both active task directories,
   archive both tasks, and record one journal session.
6. Create the exact-head completion receipt before the first push.
7. Publish and review the replacement PR. Any later remediation commit must be
   single-parent and must not change protected Trellis bookkeeping paths.

## Content Replay Contract

The replayed functional scope is:

- `.github/scripts/bookkeeping_ci_scope.py`
- `.github/scripts/check-ci-result.sh`
- `.github/workflows/tests.yml`
- `.trellis/spec/backend/quality-guidelines.md`
- `CONTRIBUTING.md`
- `Makefile`
- `tests/test_bookkeeping_ci_scope.py`
- `tests/test_generated_parity.py`
- `tests/test_release_ledger.py`

After replay, each path must be byte-identical to the same path at `3d1a827`,
unless current `main` has an intentional non-overlapping change that requires
an explicit reviewed reconciliation. Trellis task/workspace files are
regenerated from current `main` and are never copied from PR #270.

## Task Lifecycle

Current `main` still owns the original fast-lane task in planning state. The
recovery task records why a second publication was necessary. Both tasks are
activated on the replacement branch and archived in the same finalization
range. The completion validator supports multiple detected archive mappings;
the journal records one outcome and its work commits.

## Safety and Rollback

- PR #270 and its branch are read-only evidence until replacement convergence.
- No force push, history rewrite, default-branch push, or deletion is used.
- If replay or validation fails, the replacement branch can remain local while
  PR #270 stays available and unchanged.
- If `main` advances incompatibly before publication, stop before archival and
  rebuild from the new base; never merge `main` after the completion archive
  and journal tail.
- Close PR #270 only after the replacement has green exact-head CI, clean
  review state, and a valid completion receipt.
