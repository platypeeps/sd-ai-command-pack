---
title: Support fleet PR head republication after review fixes
status: done
created: 2026-07-26
branch: codex/support-fleet-pr-head-republication
---
# Support fleet PR head republication after review fixes

## Goal

Let an active fleet lane recover when a review-stage or merge-eligibility fix advances an existing PR head: preserve the failed old-head receipt, route through PR publication again, establish a new exact-head epoch, and resume normal review without editing controller state manually.

## Background

- Fleet campaign `fleet-0-54-0-20260726T143936Z` published `anomaly-metric-creator` PR #299 at `7ad0fa85749dc6251c996480dac0a120720affea`.
- CI exposed consumer-owned compatibility-test failures. The reviewed fix advanced the PR to `4417acc72faf4e2fa31977e48cc9d2cebd8f815c`, where typed checks, CI, CodeQL, and review threads are clean.
- Schema-v1 correctly rejects a review receipt for `4417acc...` because the only publication epoch records `7ad0fa...`; recording `7ad0fa...` as a passed review would be stale and false.
- Existing corrective recovery is deliberately limited to terminal merge-stage pack blockers and must not be broadened to ordinary review fixes.

## Requirements

- R1: Add one explicit, stable retry reason for an existing PR whose head advanced because review or merge-eligibility remediation required a commit.
- R2: Accept that retry only for `retryable-failure` receipts at `review` or `merge-eligibility`, bound to the currently published full head and PR number.
- R3: On the first eligible retry, preserve the old-head receipt and route the lane to a new `pr-publication` attempt instead of retrying the stale review stage.
- R4: Require the subsequent publication action to record the existing PR number and the newly classified full head; later PR-head stages must match that new epoch.
- R5: Keep generic transient retries on their current stage and keep the existing two-attempt exhaustion behavior. A second head-advance retry must park rather than create unbounded publication epochs.
- R6: Reject the special reason outside the two allowed stages, with the wrong result, without an established PR/head, or with mismatched old-head evidence; failures must not rewrite campaign state.
- R7: Preserve schema-version-1 compatibility and all historical receipts. Do not manually migrate existing campaign files.
- R8: Document the supported operator sequence and the distinction from merge-stage corrective-release recovery.
- R9: Keep this corrective change source-only. Do not change installed templates, adapters, manifests, or the immutable v0.54.0 payload in this task.

## Acceptance Criteria

- [x] A review-stage `retryable-failure` with reason `pr-head-advanced` and the published head routes to `pr-publication` attempt two while retaining the old receipt.
- [x] The same flow works from merge eligibility.
- [x] Publication attempt two may establish a different full head on the same PR, and review through post-merge receipts must match it.
- [x] Generic review retry behavior and retry exhaustion remain unchanged.
- [x] Invalid stage/result/head/PR combinations fail closed and leave serialized state unchanged.
- [x] Existing schema-v1 and corrective-recovery tests remain green.
- [x] Focused controller coverage and the full repository check pass.

## Out of Scope

- Changing the consumer PR or its installer-managed payload again.
- Weakening exact-head validation or treating a review receipt as a publication receipt.
- Expanding corrective-release recovery beyond merge-stage pack blockers.
- Shipping new adapter or skill guidance before the next normal payload release.

## Traceability

- Trigger: `anomaly-metric-creator` PR #299 during the v0.54.0 fleet campaign.
- Affected contract: `.trellis/spec/backend/manifest-and-filesystem.md`, `Scenario: Resumable Fleet Campaign Controller`.
