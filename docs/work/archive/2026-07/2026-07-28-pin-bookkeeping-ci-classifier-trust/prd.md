---
title: Pin the bookkeeping CI classifier against the PR base
status: done
created: 2026-07-28
---
# Pin the bookkeeping CI classifier against the PR base

## Goal

Stop the bookkeeping fast lane from deciding CI scope by executing classifier code read out of an attacker-controllable commit, and stop the sole required merge context from reporting green when the heavy lanes were skipped on that basis.

## Requirements

- `.github/workflows/tests.yml:148` must not execute a classifier blob from `$BEFORE_SHA` unless that blob is identical to the base branch's blob; on mismatch the workflow selects `mode: full`. Identity must be positively established, so an unresolvable or absent base sha selects `mode: full` too — "not proven identical" and "proven different" both fail closed, and `design.md` gives them distinct reason codes.
- The existing `mode`/`type`/`path` guard at tests.yml:145 is insufficient on its own and must be kept plus extended with a blob-identity comparison (`git rev-parse "$BASE_SHA:<classifier>"` versus `"$BEFORE_SHA:<classifier>"`).
- ~~`evidenceRunId` values accepted by the jq validation at tests.yml:105-106 must be resolved through the GitHub API in a trusted step.~~ **Moved out 2026-07-29** to `07-29-resolve-evidence-run-id-through-api` by maintainer decision. It was underspecified here — see the Notes below — and it is not on A-038's attack path. This task no longer carries it.
- The acceptance table in `.github/scripts/check-ci-result.sh:52` must not report success for a `pull_request` event whose heavy lanes were skipped under a classifier that failed the identity check.
- No change may weaken the existing fail-closed reasons in `.github/scripts/bookkeeping_ci_scope.py`.

## Acceptance Criteria

- [x] A test or CI rehearsal demonstrates that a PR whose first push modifies `bookkeeping_ci_scope.py` and whose second push carries payload changes selects `mode: full`. **Met 2026-07-29 by live rehearsal**, PR #278, run `30515960389`, job `90785786135`: `mode: full`, `reason: prior_classifier_not_base_identical` on a `synchronize` event whose `BEFORE_SHA` was the tamper commit and whose increment was bookkeeping-eligible. Full record in `implement.md` step 8. The complementary negative control is in step 10 — a base-identical prior classifier still reaches `mode: bookkeeping` — so the guard discriminates rather than always selecting `full`.
- ~~The `evidenceRunId` path rejects a fabricated run ID.~~ Moved with requirement 3 to `07-29-resolve-evidence-run-id-through-api`.
- [x] "CI Result" reports failure (not success) for the skipped-lane shape above. **Met on the existing assertion, not a staged live run** — `tests/test_bookkeeping_ci_scope.py:508` already asserts exit 1 for `("pull_request", "success", "full", "skipped", ...)`, which is this shape exactly. Note the literal wording describes a state the fixed workflow can no longer reach: an identity failure selects `full`, and the heavy lanes then run. Reasoning recorded in `implement.md` steps 9 and 12; no change to `check-ci-result.sh` was needed or made.
- [x] `make check` passes. Exit 0 on the final head; re-run after each task-record edit, preceded by `make sync` per `CONTRIBUTING.md:108-111`, which regenerated nothing on every run.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-038 (P0 · M · Verified · tooling).
- `concurrency` at tests.yml:9 cancels the tamper commit's own run, so the tamper commit is never linted or tested; reverting the classifier in the payload commit also erases the tamper from the reviewable diff.
- "CI Result" is the only required merge context (`tests.yml:464` job key, `:465` display name; README.md:889). Verified 2026-07-29; `:461-463` is the comment above the job, which earlier drafts cited instead.
- A-100 (`07-28-consolidate-ci-fast-lane-trust-stack`) subsumes this finding if the fast lane is retired instead of hardened. **Sequencing is already resolved: harden first.** `07-28-consolidate-ci-fast-lane-trust-stack/prd.md:27` settled it 2026-07-28 — A-038 is a live branch-protection bypass, the retain/retire call is measurement-gated with no date, and the hardening is a small change to one `run:` step that is not wasted if the lane is later retired. An earlier version of this note said "decide that first", which contradicted the sibling task and this task's own P0-first rollout in `design.md`.
- **The base anchor is `github.event.pull_request.base.sha`, not `PROTECTED_REF`.** Verified 2026-07-28: `tests.yml:52` sets `PROTECTED_REF: ${{ github.ref }}`, which on a `pull_request` event is `refs/pull/<n>/merge` — the PR author's content merged into base. Requirement 2 above is already correct in naming `BASE_SHA`; this note exists because the sibling task's design briefly named `PROTECTED_REF` and that has been corrected there. `release-payload-gate` already uses `base.sha` as `BASE_SHA` at `tests.yml:410`.
- **The guard is `pull_request`-only.** On `push` to `main`, `github.event.before` is the previous protected-branch tip, which already passed `CI Result`. No base sha exists and no threat applies.
- **Requirement 4 is satisfied structurally, not by a ninth argument.** Verified 2026-07-28: an identity failure routed through the existing `select_full` idiom writes `mode: "full"`, and `check-ci-result.sh:37-51` then requires the heavy lanes to have succeeded. The `bookkeeping)` branch at `:52` is unreachable with a failed identity check, so a ninth parameter would encode a state the workflow cannot produce. `design.md` records the alternative considered and declined.
- **Requirement 3 was split out on 2026-07-29, not dropped.** It now lives in `07-29-resolve-evidence-run-id-through-api`, which carries the full evidence and the open widen-vs-narrow decision. Two verified reasons it could not stay: as drafted it required only `head_sha == BEFORE_SHA`, which is weaker than `.trellis/spec/backend/quality-guidelines.md:1623-1626` demands and weaker than the trusted classifier already enforces at `.github/scripts/bookkeeping_ci_scope.py:290-292` and `:318-320`; and the test group the plan named cannot reach the workflow block the validation would live in — `tests/test_bookkeeping_ci_scope.py:158` calls the Python classifier, not the inline `gh api` block. Raised as concern C-14 in this task's planning adversarial review.
- **The field is published but ungated, which is why the split is safe.** Re-measured 2026-07-29, correcting an earlier draft that called it a display field with one consumer. `evidenceRunId` is written to `$GITHUB_OUTPUT` at `tests.yml:115`, **exported as a `ci-scope` job output** at `:31`, passed as `EVIDENCE_RUN_ID` at `:236`, and printed to `$GITHUB_STEP_SUMMARY` at `:249` (not `:252`, which lists avoided jobs). No job or step reads `needs.ci-scope.outputs.evidence_run_id` today, so nothing gates on it — but it is a published job output, not a local printf, so a future consumer could gate on it. The jq clause at `:105-106` is a shape check plus a "must claim evidence" check that a tampered classifier satisfies by emitting `1`. Real gap, not on A-038's attack path, and this task's P0 ships complete without it.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
