# Refresh review learnings after 0.21.4 rollout

## Goal

Capture durable review-cycle lessons from the completed 0.21.4 source and
seven-consumer rollout while the evidence is current, without turning
one-off consumer feedback into noisy pack policy.

## Background

The source repository is clean on `main` after release 0.21.4 and the fleet
preflight reports all seven consumers at target. The rollout produced several
pack-owned corrective releases and one non-blocking Copilot hardening idea,
which is already recorded as the planned
`status-snapshot-contract-validation` task. The repository owns a managed
review-learning block in `docs/review-learnings.md` and a local scanner that
can inspect both the working tree and recent GitHub review comments.

## Requirements

- Run the local review-learning scan against the current working tree.
- Inspect the complete recent GitHub review window covering the source PRs
  involved in the rollout; do not impose an arbitrary PR count limit.
- Update only the managed `sd-review-learnings` block in
  `docs/review-learnings.md`, preserving human-authored content.
- Distinguish repeated, preventable pack patterns from one-off consumer
  integration findings and already-tracked follow-up work.
- Promote any newly identified reusable prevention into the appropriate pack
  source of truth or a detailed Trellis task; do not duplicate the existing
  snapshot-contract task.
- Keep this task limited to review-learning capture and directly necessary
  preventive bookkeeping. Shipped behavior changes require their own task and
  release cycle.

## Acceptance Criteria

- [x] The local working-tree scan completes and its findings are recorded.
- [x] Recent GitHub Copilot review comments are scanned across the complete
      selected time window.
- [x] The managed learning block is refreshed without modifying surrounding
      human-authored content.
- [x] Every actionable learning is either already prevented, implemented as
      small local guidance, or linked to a non-duplicate Trellis task.
- [x] Repository checks relevant to the changed documentation and task
      artifacts pass.
- [x] The final report summarizes the detected patterns, preventive coverage,
      and any remaining follow-up.

## Results

- The working-tree scan found no local mechanical review-cycle pattern.
- The untruncated two-day GitHub scan inspected 25 pull requests and captured
  54 Copilot comments. After verification, every captured signal is resolved
  or outdated; the managed block contains no current unresolved signal.
- Three unresolved threads from merged PR #154 were verified directly. The
  relative-path implementation and regression test exist in the current
  source, while the archived rollout task deliberately preserves its original
  0.19.3 identity and documents its progression through 0.19.11. Evidence was
  posted and all three threads were resolved.
- Existing prevention covers the repeated themes: source/template parity,
  focused regression tests, exact-head comment-clean review gates, fast-first
  sequential fleet rollout, stop-and-release behavior for pack defects, and a
  post-cycle review-learning pass.
- The only non-blocking rollout hardening idea is already tracked by
  `07-19-status-snapshot-contract-validation`; no duplicate task or shipped
  behavior change is justified by this review.

## Out Of Scope

- Reopening or changing already merged consumer PRs.
- Patching provenance-managed consumer payloads directly.
- Creating a pull request in the upstream Trellis repository.
