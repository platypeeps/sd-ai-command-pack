# Batch source defect sweeps before corrective fleet releases

## Goal

Batch related source-owned defects into one deliberate corrective release
instead of immediately tagging and restarting the fleet after each individual
review comment.

## Background

- The 0.23.1 rollout advanced repeatedly through 0.23.11 as consumer reviews
  found related work-loop validation, reconciliation, snapshot, CLI, and status
  gaps one at a time.
- Narrow fixes followed by immediate release and re-review turned Copilot into
  a serial stochastic fuzzer and expanded the corrective chain to more than
  eight hours.
- Full-fleet candidate validation is payload-bound and should remain the final
  release gate, but diagnostic iteration can be focused before that final run.

## Requirements

- When a consumer surfaces a pack-owned blocker, pause fleet mutation and open
  a source-owned corrective stream before preparing another release.
- Require a defect-cluster sweep of the affected contract surface. The sweep
  must enumerate equivalent mutation paths, normalization boundaries, field
  families, serialization and status projections, CLI exposure, and error
  behavior where applicable.
- Record each discovered issue, its severity, evidence, and disposition before
  selecting the corrective version.
- Permit focused source tests and partial consumer candidate diagnostics during
  iteration. Partial runs must never replace the canonical candidate ledger.
- Run one canonical all-consumer candidate validation after the corrective
  payload is stable and before the release is merged or tagged.
- Avoid a new version bump for each related finding in the same paused
  corrective stream. An urgent independent security fix may ship separately
  when delaying it would increase risk.
- Document the workflow in the fleet guide and synchronize affected skills,
  templates, and tests.

## Acceptance Criteria

- [x] The first pack-owned blocker pauses the fleet and produces a documented
      contract-surface sweep before another tag is created.
- [x] Multiple related findings can be resolved under one corrective version.
- [x] Focused diagnostic candidate runs cannot overwrite the canonical ledger.
- [x] Exactly one successful full-fleet candidate run is required for the final
      corrective payload.
- [x] Tests cover batching, an urgent-security exception, and resuming the
      original fleet task after release.
- [x] The final report preserves every finding and disposition without creating
      duplicate rollout tasks.

## Dependencies

- Coordinate with `07-20-fleet-interruption-severity-gate` so the batching flow
  operates only on findings that actually justify interrupting the fleet.

## Out of Scope

- Holding an urgent security fix solely to accumulate more findings.
- Combining unrelated consumer product changes with a pack correction.

## Notes

- Add `design.md` and `implement.md` before starting implementation.
