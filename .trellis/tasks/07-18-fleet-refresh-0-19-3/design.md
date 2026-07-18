# Fleet Refresh 0.19.8 Design

## Boundaries

The pack source checkout owns target-version discovery, fleet ordering,
preflight, installation, and aggregate reporting. Each consumer checkout owns
its product-specific full-check, pull request, CI, review state, merge gate,
and post-merge cleanup.

The rollout changes only installer-managed pack payload and deterministic
generated artifacts required by a consumer's documented gate. Product code and
unrelated local state are out of scope.

## Control Flow

1. Source preflight reads `manifest.json` and `docs/fleet/consumers.json`, then
   classifies consumers as at-target, refresh-needed, or unavailable/blocked.
2. Refresh-needed consumers are processed sequentially in manifest priority
   order. No second consumer starts while the first has an unresolved rollout
   state.
3. A consumer branch receives the source checkout's tagged payload through
   `install.py --force` with the manifest-selected platforms.
4. The source-owned install audit verifies platform completeness and
   provenance before the consumer-owned full-check runs.
5. A successful local gate is published to a consumer PR. The PR is watched
   until CI and review settle, then merged only through that consumer's
   housekeeping gate.
6. Post-merge provenance and audit close the consumer result before advancing.

## Failure Model

- Dirty or missing consumer checkouts are isolated skips; no mutation occurs.
- Consumer-local full-check failures leave the refresh branch for inspection,
  do not open a PR, and allow the rollout to continue unless they expose a
  released-pack defect.
- Correctness, security, install/audit, or compatibility defects in the tagged
  pack stop the entire rollout so the source release can be corrected.
- GitHub policy, CI, or unresolved-review blockers leave the consumer result
  explicit and prevent its merge.

## Recovery And Rollback

Rerunning preflight is the recovery mechanism: merged consumers read as
at-target and are skipped. Unmerged consumer branches remain available for
inspection. The process never resets, stashes, force-pushes, or installs over a
dirty checkout.

Rollback of a bad released payload is a new patch release followed by another
fleet refresh; consumer history is not rewritten.

This recovery path was exercised before the first merge: Loadsmith integration
review found a pack-owned defect in 0.19.3, so the rollout stopped. The first
correction merged as 0.19.4 but was not tagged after its squash merge exposed a
main-push guard defect. Source review then accumulated the complete correction
into 0.19.8; a new full-fleet candidate check must replace the stale release
ledger before rollout resumes.

## Verification

The rollout uses three evidence layers: source preflight and candidate-ledger
validity, per-consumer install audit plus full-check, and post-merge provenance
plus audit. GitHub checks and thread-aware review state gate every merge.
