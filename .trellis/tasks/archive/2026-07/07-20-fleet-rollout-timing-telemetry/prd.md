# Record fleet rollout stage timing telemetry

## Goal

Make fleet cycle-time bottlenecks directly measurable with stable,
machine-readable stage timing and a concise human summary.

## Background

- The 0.23.11 retrospective required reconstructing timing from tags, journal
  entries, and GitHub PR timestamps.
- Reviewer wait and CI often overlap, so total duration alone cannot identify
  the critical path or quantify the benefit of skipping a redundant review.
- Timing must remain local and repository-owned; no external telemetry service
  is required.

## Requirements

- Capture monotonic elapsed duration and wall-clock boundaries for preflight,
  checkout validation, install, audit, local gate, commit and push, PR creation,
  reviewer wait, CI wait, housekeeping, and post-merge audit where applicable.
- Model reviewer and CI intervals independently so overlapping wait is not
  double-counted. Report both per-stage elapsed time and consumer critical-path
  duration.
- Record target version, consumer identity, outcome, retry count, and skip or
  failure reason without including secrets, credentials, or personal absolute
  paths.
- Define and validate a versioned machine-readable schema plus a concise final
  fleet summary sorted in manifest order.
- Preserve partial timing when a run is interrupted and continue the same
  record on resume without duplicating completed stages.
- Timing collection failures must be visible but must not corrupt rollout
  state or silently convert a failed gate into success.
- Add deterministic tests using an injectable or fake clock.
- Document how to compare a sequential baseline with later review-policy and
  rollout-wave changes.

## Acceptance Criteria

- [x] A completed fleet run reports every applicable stage per consumer and the
      aggregate critical path.
- [x] Concurrent reviewer and CI waits are represented as overlapping intervals
      rather than summed wall time.
- [x] Interrupted and resumed runs retain one coherent timing record.
- [x] Reports contain no credentials or personal absolute paths.
- [x] Schema validation rejects malformed records with actionable diagnostics.
- [x] Fake-clock tests cover success, skip, failure, retry, overlap, and resume.
- [x] The human report makes the slowest consumer and slowest stage obvious.

## Dependencies

- Land before or alongside `07-20-fleet-post-canary-waves` to capture a useful
  sequential baseline and verify the wave improvement.

## Out of Scope

- Sending telemetry to a hosted analytics or monitoring service.
- Product-level performance instrumentation inside consumer applications.

## Notes

- Add `design.md` and `implement.md` before starting implementation.
- Delivered in PR #188, merged on 2026-07-20 from final reviewed head
  `a29ce9732a835e64d9db6969bc812e95654d4612`.
- Validation recorded on the delivery PR: `make check`, canonical unfiltered
  candidate validation across all seven consumers, and 133 focused timing,
  orchestration, install, and parity tests.
- All required GitHub checks passed on the final head, and the final configured
  Copilot review reported no new comments.
