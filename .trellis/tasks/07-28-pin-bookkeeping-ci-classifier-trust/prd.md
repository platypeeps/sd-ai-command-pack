# Pin the bookkeeping CI classifier against the PR base

## Goal

Stop the bookkeeping fast lane from deciding CI scope by executing classifier code read out of an attacker-controllable commit, and stop the sole required merge context from reporting green when the heavy lanes were skipped on that basis.

## Requirements

- `.github/workflows/tests.yml:148` must not execute a classifier blob from `$BEFORE_SHA` unless that blob is identical to the base branch's blob; on mismatch the workflow selects `mode: full`.
- The existing `mode`/`type`/`path` guard at tests.yml:145 is insufficient on its own and must be kept plus extended with a blob-identity comparison (`git rev-parse "$BASE_SHA:<classifier>"` versus `"$BEFORE_SHA:<classifier>"`).
- `evidenceRunId` values accepted by the jq validation at tests.yml:105 must be resolved through the GitHub API in a trusted step, not accepted as any positive integer.
- The acceptance table in `.github/scripts/check-ci-result.sh:52` must not report success for a `pull_request` event whose heavy lanes were skipped under a classifier that failed the identity check.
- No change may weaken the existing fail-closed reasons in `.github/scripts/bookkeeping_ci_scope.py`.

## Acceptance Criteria

- [ ] A test or CI rehearsal demonstrates that a PR whose first push modifies `bookkeeping_ci_scope.py` and whose second push carries payload changes selects `mode: full`.
- [ ] The `evidenceRunId` path rejects a fabricated run ID.
- [ ] "CI Result" reports failure (not success) for the skipped-lane shape above.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-038 (P0 · M · Verified · tooling).
- `concurrency` at tests.yml:9 cancels the tamper commit's own run, so the tamper commit is never linted or tested; reverting the classifier in the payload commit also erases the tamper from the reviewable diff.
- "CI Result" is the only required merge context (tests.yml:461, README.md:889).
- A-100 (`07-28-consolidate-ci-fast-lane-trust-stack`) subsumes this finding if the fast lane is retired instead of hardened. Decide that first if both are scheduled together.
- **The base anchor is `github.event.pull_request.base.sha`, not `PROTECTED_REF`.** Verified 2026-07-28: `tests.yml:52` sets `PROTECTED_REF: ${{ github.ref }}`, which on a `pull_request` event is `refs/pull/<n>/merge` — the PR author's content merged into base. Requirement 2 above is already correct in naming `BASE_SHA`; this note exists because the sibling task's design briefly named `PROTECTED_REF` and that has been corrected there. `release-payload-gate` already uses `base.sha` as `BASE_SHA` at `tests.yml:410`.
- **The guard is `pull_request`-only.** On `push` to `main`, `github.event.before` is the previous protected-branch tip, which already passed `CI Result`. No base sha exists and no threat applies.
- **Requirement 4 is satisfied structurally, not by a ninth argument.** Verified 2026-07-28: an identity failure routed through the existing `select_full` idiom writes `mode: "full"`, and `check-ci-result.sh:37-51` then requires the heavy lanes to have succeeded. The `bookkeeping)` branch at `:52` is unreachable with a failed identity check, so a ninth parameter would encode a state the workflow cannot produce. `design.md` records the alternative considered and declined.
- **Requirement 3 guards a display field.** Measured 2026-07-28: `evidenceRunId`'s only non-test consumer is a `printf` into `$GITHUB_STEP_SUMMARY` at `tests.yml:252`. Nothing gates on it; the jq clause at `:105-106` is a shape check plus a "must claim evidence" check that a tampered classifier satisfies by emitting `1`. Worth doing, but it is not on A-038's attack path and must not delay the P0 fix.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
