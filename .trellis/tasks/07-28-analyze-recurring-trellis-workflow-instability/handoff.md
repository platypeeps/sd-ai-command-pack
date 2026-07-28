# New-session handoff

## Purpose and current state

This is the canonical continuation surface for the recurring Trellis workflow
instability investigation. The evidence review is complete and the accepted
work is decomposed into planning tasks. No implementation task was started in
this session.

Current investigation task:
`07-28-analyze-recurring-trellis-workflow-instability` (`planning`, P1).

Read in this order:

1. This file for ownership, state, and sequence.
2. `research/recent-trellis-workflow-instability.md` for evidence and root
   causes.
3. `design.md` and `implement.md` for accepted boundaries and ordering.
4. The selected child or related task's own PRD/design/implementation plan
   before starting it.

## Finding ownership

| Finding | Required follow-up | Durable owner | State |
| --- | --- | --- | --- |
| F1: multi-epoch completion protocol | Add planning-only finalization; clarify pre/post-archive obligations; enforce readiness; harden receipt/schema; verify integration | `07-24-support-planning-only-pr-finalization`; `07-28-clarify-completion-housekeeping-obligations`; `07-28-enforce-pre-archive-acceptance-readiness`; `07-28-decide-housekeeping-result-schema-compatibility`; `07-28-validate-finish-work-receipt-path`; `07-22-validate-sd-workflow-program-integration` | Planning; explicit dependencies are recorded in the task documents |
| F2: recorder/validator mismatch | Preserve the pack-local wrapper; handle producer commit subjects and retry convergence independently in the local Trellis checkout | Upstream-repository task `07-28-harden-add-session-retry-convergence`; existing `07-23-align-task-validation-preflight` owns `_example`; existing `07-27-track-journal-evidence-contradictions` owns evidence coordination | Non-blocking local lane; no new pack task needed without a current-version reproducer |
| F3: cleanup-only eligibility anomaly | Route housekeeping by PR lifecycle state before eligibility | `07-28-route-housekeeping-by-pr-lifecycle-state` | Planning, P1 |
| F4: work-loop persistence/recovery | Fix stale-lock race; expose blocked ordering; retain owned recovery artifacts | `07-25-fix-work-loop-lock-race`; `07-25-backlog-selector-blocked-markers`; `07-24-track-clean-recovery-artifacts` | Planning |
| F5: environment failures misclassified | Add typed `environment_blocked` checkpoints; harden user cache ownership; retain recovery artifacts | `07-28-standardize-environment-blocked-recovery-evidence`; `07-25-user-scope-toolchain-caches`; `07-24-track-clean-recovery-artifacts` | Planning; do not widen `07-25-harden-toolchain-failure-paths` |
| F6: fleet version skew | Accept temporary 0.55.5 skew; after pack remediation and integration, deploy the stabilized successor release once | `07-28-roll-out-stabilized-pack-release-to-fleet` | Planning, P1; explicitly blocked on the pack fixes, final integration, and successor release |
| F7: upstream checkout bypasses pack guards | Reconcile completed task outside archive and restore the safe OpenCode reader locally | Existing Trellis-checkout task `07-24-fix-task-context-jsonl-warning-syntax` is the exact cleanup artifact; `07-28-restore-install-safe-opencode-mem-reader` owns reader restoration; `07-27-validate-task-branch-metadata-before-archive`, `07-27-track-no-active-task-completion-receipts`, and `07-27-track-archive-repo-map-drift` remain adjacent safeguards | Non-blocking local lane; no upstream PR is authorized |

Every finding now has a task owner or an explicit existing artifact whose own
lifecycle is the required follow-up. There is no unowned implementation gap in
the accepted recommendation set.

## Delivery boundary

`07-28-stabilize-self-hosted-delivery-lifecycle` owns one branch, PR,
completion bundle, and merge for every pack-owned remediation in F1, F3, F4,
and F5. The tasks in the table remain independently verifiable work-package
contracts on that shared branch. No planning-only or intermediate
implementation PR is allowed. The bounded umbrella stability matrix is the
successor-release gate; the broader program-integration task consumes its
evidence later.

## Operational items that are not new implementation tasks

- Review the current planning changes, then commit them as the first bounded
  commit on the umbrella stabilization branch. Do not publish or merge them
  through a separate planning-only PR.
- Unrelated task `07-28-bound-review-learnings-unsafe-path-diagnostics` is
  preserved outside the umbrella at commit `22aa265` on local branch
  `codex/plan-bound-review-learnings-unsafe-path-diagnostics`. Do not merge or
  cherry-pick it into the stabilization branch.
- The upstream Trellis checkout contains the two new planning task directories
  `07-28-harden-add-session-retry-convergence` and
  `07-28-restore-install-safe-opencode-mem-reader`. They are not active and
  remain unpublished.
- Reconcile/archive upstream completed task
  `07-24-fix-task-context-jsonl-warning-syntax` through Trellis's own workflow;
  do not create a duplicate task for the same cleanup.
- Do not create an upstream Trellis PR without separate explicit approval for
  that specific PR.
- OpenCode sessions were excluded from the evidence inventory because Trellis
  0.6.7 cannot index them safely; the restoration task above preserves that
  limitation as tracked work.

## Recommended next sequence

1. Review and approve `07-28-stabilize-self-hosted-delivery-lifecycle`.
2. Create its one feature branch and commit this complete planning/handoff
   surface as the first branch commit without opening a planning PR.
3. Execute all eleven work packages as focused commits with package tests,
   local reviews, and `progress.md` checkpoints; do not finalize or merge
   between packages.
4. Run the cumulative self-hosting matrix and release preparation, then use one
   multi-task completion bundle, exact-head review cycle, and housekeeping
   merge.
5. Publish the stabilized successor release and execute
   `07-28-roll-out-stabilized-pack-release-to-fleet` once.

Handle the Trellis-checkout tasks locally in a separate, non-blocking lane.
Only a reproducible final-integration safety failure that cannot be mitigated
locally may make one a release dependency. Any upstream publication still
requires separate consent for that specific PR.

## New-session entry

From the `sd-ai-command-pack` repository root:

1. Run `sd-status` to refresh Git, task, and fleet evidence.
2. Use `trellis-continue` or `sd-continue` and select
   `07-28-analyze-recurring-trellis-workflow-instability` if the planning
   handoff itself needs review.
3. Otherwise select the next task from the sequence above and review its
   PRD/design/implementation plan before starting it.
4. Validate this planning task with
   `python3 .trellis/scripts/task.py validate 07-28-analyze-recurring-trellis-workflow-instability`.

## Decisions already accepted

- Keep command-pack and upstream Trellis ownership separate.
- Model environment restrictions as typed, bounded recovery evidence; never
  auto-escalate privileges or broaden retries.
- For unresolved commit metadata, fail before mutation unless an explicit
  validated commit-OID-to-subject mapping is supplied.
- Keep exact-head review, CI, finish-work, housekeeping, and deletion proof
  fail closed.
- Use separate focused tasks rather than expanding the narrow
  `07-25-harden-toolchain-failure-paths` scope.
- Accept temporary fleet version skew instead of distributing known partial
  behavior; remediation, integration, and release precede fleet deployment.
- Keep Trellis-checkout fixes local and non-blocking unless final integration
  proves an upstream dependency is absolutely required.
- Deliver all pack-owned stability fixes through one umbrella merge while
  retaining focused commits, task contracts, tests, and local review gates.
