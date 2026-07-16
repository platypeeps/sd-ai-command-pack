# Roll out sd-ai-command-pack 0.15.0 to the fleet

## Goal

Sequentially refresh every stale consumer in docs/fleet/consumers.json to sd-ai-command-pack 0.15.0 using fleet preflight, installer audit, consumer full-check, PR review, gated merge, post-merge provenance verification, and housekeeping.

## Requirements

- Treat `docs/FLEET_ROLLOUT.md` and `docs/fleet/consumers.json` as the rollout
  authorities; target the tagged `v0.15.0` release from this checkout.
- Run the source-owned fleet preflight before consumer mutation and again after
  the rollout to produce before/after version evidence.
- Process all six manifest consumers strictly sequentially. Never mutate a
  dirty checkout, create a missing clone, or touch consumer product code.
- For each stale clean consumer, create a refresh branch from its current
  default branch; run the preflight-provided install and expected-platform
  audit commands; then run the consumer's documented full-check gate.
- Open a consumer PR only after local validation passes. Merge only through
  that consumer's green, comment-clean housekeeping gate, without force pushes
  or forced merges.
- After each merge, confirm target-version provenance and a passing install
  audit, return the checkout to a clean default branch, and remove the refresh
  branch before proceeding.
- Record every skip, open PR, validation failure, and anomaly explicitly.

## Acceptance Criteria

- [ ] The release tag `v0.15.0` resolves to the merged pack release commit.
- [ ] Every manifest consumer is classified with its before version and final
  result: `at-target`, `refreshed+merged`, `PR-open`, or `skipped+<reason>`.
- [ ] Every refreshed consumer has a passing expected-platform install audit
  and consumer full-check before PR creation.
- [ ] Every merged consumer is green and comment-clean, and post-merge
  provenance reports `0.15.0` with a passing install audit.
- [ ] Every touched consumer checkout ends clean on its default branch matching
  the remote, with the refresh branch removed locally and remotely.
- [ ] A final fleet preflight and status table identify any remaining stale
  consumer and the exact follow-up required; otherwise all six are at target.

## Notes

- This is operational rollout work. Consumer product changes and upstream
  Trellis changes are out of scope.
- The Answerbook consumer remains in scope because it is explicitly present in
  the checked-in fleet manifest.
