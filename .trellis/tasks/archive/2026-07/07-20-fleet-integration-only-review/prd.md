# Enforce integration-only review for pure fleet refreshes

## Goal

Reduce clean fleet-refresh cycle time by enforcing the documented review
ownership boundary: pack implementation is reviewed in the source repository,
while a pure consumer refresh is reviewed only for its installed integration.

## Background

- `docs/FLEET_ROLLOUT.md` assigns pack-owned implementation review to the
  source PR and limits consumer review to platform wiring, receipts,
  provenance, secrets, documentation accuracy, and consumer-owned changes.
- The generic `sd-review-pr` flow requests the configured remote reviewer on
  every new review-fix head. During the 0.23.11 rollout, this caused unchanged
  vendored implementation to receive repeated line-level review in consumers.
- The final pure 0.23.11 refresh PRs passed their deterministic gates and
  received no new Copilot comments.

## Requirements

- Define a fail-closed classification for a pure installer-managed refresh.
  The classification must require a valid released payload and candidate
  ledger, an exact install audit, and a diff limited to installer-managed
  payload, receipts, provenance, and managed blocks.
- Make `sd-fleet-refresh` use an integration-only review path for qualifying
  PRs. It must not request a new remote implementation review, but it must
  still inspect existing comments and unresolved review threads.
- Continue to require the consumer's local gate, required GitHub checks,
  mergeability, head identity, and the normal housekeeping merge gate.
- Fall back to the normal remote-review flow when classification is ambiguous,
  consumer-owned files changed, the audit is not exact, or the operator
  explicitly requests remote review.
- Keep source PR remote review unchanged.
- Update the source documentation, shipped skill/template surfaces, command
  help, and regression tests together.

## Acceptance Criteria

- [ ] A pure installer-managed refresh reaches merge readiness without
      requesting Copilot or another configured remote reviewer.
- [ ] Existing unresolved review threads still block the refresh.
- [ ] Consumer-owned or ambiguous changes route through the existing remote
      review convergence flow.
- [ ] Audit, provenance, local checks, GitHub CI, and housekeeping remain
      mandatory.
- [ ] Tests cover qualifying, non-qualifying, explicit-override, and stale or
      invalid candidate-ledger cases.
- [ ] Generated templates and installed mirrors remain synchronized.

## Out of Scope

- Weakening review requirements for source implementation PRs.
- Ignoring existing reviewer feedback or merging a red consumer PR.
- Broad changes to GitHub branch-protection policy.

## Notes

- Add `design.md` and `implement.md` before starting implementation.
