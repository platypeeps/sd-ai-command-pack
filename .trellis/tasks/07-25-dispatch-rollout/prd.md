# Roll out dispatch protocols to sd-test-gaps, sd-update-deps, sd-fleet-refresh

Parent: `.trellis/tasks/07-25-agent-artifacts` (Tier 1 rollout). Settled inputs: parent
`design.md` section 1 and `research/cross-platform-agent-support.md`.

## Goal

Extend the validated per-unit dispatch pattern to three more commands: sd-test-gaps
(per-file test authoring), sd-update-deps (per-PR classification only), and
sd-fleet-refresh (per-repo workers inside controller waves).

## Requirements

- R1: Apply the pattern validated in 07-25-fix-ci-dispatch (capability-first prose, inline
  fallback, trust restatement, parent-owned assembly). Divergences require a recorded
  reason.
- R2: sd-test-gaps: one worker per ranked gap file (bounded by `max-gaps`); worker authors
  tests for its file only; parent re-measures coverage and owns the report.
- R3: sd-update-deps: ONLY the 4-axis per-PR classification parallelizes. Merges remain
  strictly sequential — the existing "never merge dependency PRs in parallel" rule is
  restated inside the dispatch section.
- R4: sd-fleet-refresh: workers operate per consumer repo within waves planned by the
  existing deterministic controller; the controller remains the sole owner of the campaign
  ledger and timing records; serialized housekeeping merges unchanged.
- R5: Deliberate serializations elsewhere stay untouched (sd-work-backlog task loop,
  sd-housekeeping collector).

## Acceptance Criteria

- [ ] All three command bodies carry dispatch sections; `make generate` byte-stable;
      catalog regenerated.
- [ ] sd-update-deps merge-serialization rule verifiably present in the new text.
- [ ] Fleet controller contract unchanged (scripts untouched or additively extended).
- [ ] Version bump + changelog; pattern-conformance note recorded before archive.

## Dependencies / order

- BLOCKED until 07-25-fix-ci-dispatch is completed and reviewed.

## Notes

- Medium task; per-command review of unit boundaries required.
