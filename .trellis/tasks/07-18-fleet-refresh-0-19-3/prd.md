# Roll out sd-ai-command-pack 0.19.4 to the fleet

## Goal

Refresh every stale registered consumer to corrected pack release 0.19.4 using the sequential fleet rollout procedure.

## Confirmed Facts

- The rollout began from tagged release `0.19.3`.
- Loadsmith PR #90 exposed a pack-owned `sd-status` defect: repository
  resolution passed file inputs directly to `git -C` instead of using the
  containing directory.
- The rollout stopped before any consumer merge and moved to corrective
  release `0.19.4`, which fixes the defect with regression coverage.
- The full-fleet 0.19.4 candidate check passed all seven consumers and updated
  `docs/fleet/candidate-validation.json`.
- `docs/fleet/consumers.json` registers seven consumers and defines their
  fast-first rollout order.
- The full-fleet candidate ledger is a release prerequisite and is checked by
  fleet preflight before consumer mutation.

## Requirements

- Use tagged release `0.19.4` from the clean `sd-ai-command-pack` `main`
  checkout as the only installation source.
- Cover every consumer selected by `docs/fleet/consumers.json` in its declared
  rollout-priority order.
- Skip consumers already at the target version without creating empty refresh
  branches or pull requests.
- Never modify a consumer with a dirty working tree or a missing local clone;
  report the consumer and reason instead.
- Limit consumer changes to installer-owned payloads, receipts, provenance,
  and deterministic generated artifacts required by the consumer gate.
- Require install audit, the consumer's full-check, green CI, a settled review
  state, and no unresolved review threads before each merge.
- Stop the rollout for released-pack correctness, security, installation,
  audit, or compatibility defects. Record unrelated or low-risk consumer
  findings without forcing another release.
- Keep rollout status recoverable so an interrupted rerun skips consumers that
  have already reached `0.19.4`.

## Acceptance Criteria

- [ ] Fleet preflight validates the release and reports every selected
  consumer with its starting version and disposition.
- [ ] Every stale, clean, locally available consumer is refreshed sequentially
  through install, audit, full-check, pull request, review/watch, gated merge,
  and housekeeping.
- [ ] Post-merge provenance and install audit confirm `0.19.4` for every
  successfully refreshed consumer.
- [ ] Every at-target or skipped consumer is explicitly recorded; no consumer
  is silently omitted.
- [ ] The final report lists each consumer's before-version and one of
  `at-target`, `refreshed+merged`, `PR-open`, or `skipped+<reason>`.
- [ ] Remaining stale consumers, open refresh PRs, and anomalies are listed as
  follow-ups, or the report states that none remain.

## Out Of Scope

- Product-code changes in consumer repositories.
- Unattended rollout automation or creation of missing consumer clones.
- Rewriting consumer history, force-merging blocked PRs, or cleaning unrelated
  local state.
- Changes to the upstream Trellis repository.

## Notes

- Procedure authority: `docs/FLEET_ROLLOUT.md`.
- User approved task creation for this rollout on 2026-07-18.
