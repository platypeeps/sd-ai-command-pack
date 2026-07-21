# Run post-canary fleet refreshes in controlled waves

## Goal

Reduce post-tag fleet wall-clock time by overlapping independent consumer work
after the manifest-defined canary cohort proves the released payload is healthy.

## Background

- The current fleet skill processes all consumers strictly sequentially.
- The final 0.23.11 pass took about 57 minutes even though the released payload
  had already passed seven disposable candidate validations.
- Consumer repositories are independent, but a source-owned blocker found in a
  canary must still stop later fleet mutation.

## Requirements

- Keep the manifest-defined canary cohort sequential. Do not begin a later wave
  until every canary is merged, audited, and free of pack-owned blockers.
- Represent post-canary wave membership and any solo or last-consumer policy in
  versioned fleet configuration rather than hard-coded orchestration order.
- Allow install, audit, local validation, PR creation, review waiting, and CI to
  overlap across independent consumers in a bounded wave. Default concurrency
  must be conservative and explicitly configurable.
- Keep each repository's mutation stream isolated: one branch, one PR, and one
  housekeeping owner per consumer, with no interleaved writes to the same
  checkout.
- Merge only through each consumer's existing green and comment-clean
  housekeeping gate. Prefer deterministic manifest order for merge decisions
  even when validation and CI overlap.
- If any in-flight consumer finds a pack-owned blocker, stop starting new work
  and prevent unsettled wave PRs from merging until the finding is classified.
- Make interruption and resume idempotent; completed consumers remain
  `at-target`, open PRs are reported, and failed or dirty consumers retain
  precise outcomes.
- Add orchestration tests for success, partial failure, blocker propagation,
  resume, and bounded concurrency.

## Acceptance Criteria

- [x] Canary consumers remain strictly sequential and gate later waves.
- [x] At least two eligible post-canary consumers can have validation or CI in
      flight concurrently without sharing mutable checkout state.
- [x] A pack-owned blocker prevents new work and later merges across the wave.
- [x] Housekeeping and post-merge audit remain per-consumer mandatory gates.
- [x] Interrupted runs resume without duplicate branches or PRs.
- [x] The final report preserves manifest order and every consumer outcome.
- [x] Tests demonstrate the concurrency bound and deterministic failure
      handling.

## Dependencies

- `07-20-fleet-release-identity-guard` must land before concurrent mutation is
  enabled.
- Coordinate with `07-20-fleet-rollout-timing-telemetry` so the sequential
  baseline and wave critical path can be compared.

## Out of Scope

- Unbounded parallelism or parallel writes within one consumer checkout.
- Bypassing canary, review-thread, CI, mergeability, or housekeeping gates.

## Notes

- Add `design.md` and `implement.md` before starting implementation.
