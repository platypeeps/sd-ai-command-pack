# Consolidate or retire the bookkeeping CI fast-lane trust stack

## Goal

Decide whether ~600 lines of security-sensitive CI glue repay the minutes they save, and either retire the fast lane or move its correctness risk out of the hardest-to-test layer.

## Requirements

- Measure the CI minutes actually saved by the bookkeeping skip over a representative window, and record the number in the task.
- If retained: move the receipt validation and the `ls-tree` guard out of inline workflow bash (`.github/workflows/tests.yml:57`, ~200 lines of bash plus multi-clause jq, covered by no unit test) into `.github/scripts/bookkeeping_ci_scope.py` as one testable entry point, and unit-test it.
- If retired: remove the skip path, `check-ci-result.sh`'s eight-argument acceptance table, and the classifier, and let all lanes run.
- Either outcome must resolve A-038 (the P0 branch-protection bypass) and A-041 (the triplicated, already-drifted chore-scope allowlist).

## Acceptance Criteria

- [ ] The measured saving is recorded and the retain-or-retire decision is written down with that number.
- [ ] If retained: the receipt validation and ls-tree guard have unit tests and no trust decision remains in inline workflow bash.
- [ ] A-038's failure scenario no longer reproduces.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-100 (P3 · L · Plausible · correctness).
- Three layers today: tests.yml inline bash + jq, `bookkeeping_ci_scope.py` (477 lines), `check-ci-result.sh` (73 lines).
- `07-24-add-bookkeeping-only-ci-fast-lane` (the task that built this) is archived; nothing active owns the consolidation.
- Sequencing: decide this before doing A-038's hardening work (`07-28-pin-bookkeeping-ci-classifier-trust`) if both are scheduled together, since retirement makes that work moot. If A-038 is urgent, harden first and revisit here.
- **Sequencing resolved 2026-07-28: harden first.** A-038 is P0 · Verified and is a branch-protection bypass; the retain/retire call is measurement-gated with no date. The hardening is a small change to one `run:` step (compare the classifier's blob hash at `BEFORE_SHA` against the PR base and select full mode on mismatch) and is not wasted if the lane is later retired. `design.md` carries the reasoning; `07-28-pin-bookkeeping-ci-classifier-trust` owns the change.
- **Correction 2026-07-28:** an earlier revision of `design.md` named `PROTECTED_REF` (`tests.yml:52`) as the trusted source. It is `${{ github.ref }}`, which on a `pull_request` event is `refs/pull/<n>/merge` — the PR author's content merged into base — so it is not a trust anchor on the event type where the fast lane engages. The anchor is `github.event.pull_request.base.sha`, already used as `BASE_SHA` at `tests.yml:410`.
- **A-041 re-derived 2026-07-28 and confirmed exactly as stated.** `.githooks/pre-push:54` and `.github/scripts/check-main-push-scope.sh:71` each allow `.trellis/tasks/*`, `.trellis/workspace/*`, `.trellis/audit/*`; `bookkeeping_ci_scope.py:26` allows only the first two. The copies also differ mechanically — shell `case` globs versus Python string prefixes — so unifying the value does not unify the matching semantics.
- Composes with `07-28-measure-unmeasured-runtime-surface` R1: logic moved from inline workflow bash into `.github/scripts/*.py` becomes coverage-measured; logic left in a `run:` block never can be.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.

## Absorbed: 07-29-resolve-evidence-run-id-through-api (2026-08-08 consolidation)

That task hardened one member of this trust stack: the `ci-scope` publish gate
accepts any positive integer as `evidenceRunId` (`tests.yml:105-106`); the fix
would resolve it against the GitHub API in a trusted step, with failures
routing through `select_full` (never `exit 1`). Its widen-vs-narrow decision
and workflow-block test-harness constraint are recorded in its original prd.md
(recoverable via git history at
`.trellis/tasks/07-29-resolve-evidence-run-id-through-api/`).

Consolidation note: this work is **moot if the stack is retired** — nothing
reads `needs.ci-scope.outputs.evidence_run_id` today, so nothing gates on the
value. Decide retain-vs-retire for the fast-lane trust stack FIRST; only if
retained does the evidenceRunId hardening enter this task's scope.
