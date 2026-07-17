# Roll out sd-ai-command-pack 0.15.5 to the fleet

## Goal

Sequentially refresh every stale consumer in docs/fleet/consumers.json to sd-ai-command-pack 0.15.5 using fleet preflight, installer audit, consumer full-check, PR review, gated merge, post-merge provenance verification, and housekeeping.

## Requirements

- Treat `docs/FLEET_ROLLOUT.md` and `docs/fleet/consumers.json` as the rollout
  authorities; target the tagged `v0.15.5` release from this checkout.
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

- [x] The release tag `v0.15.5` resolves to merged pack release commit
  `9ef21509ad063221dcdbb73690a9aecda54dbaf4` from PR #138.
- [x] Every manifest consumer is classified with its before version and final
  result: `at-target`, `refreshed+merged`, `PR-open`, or `skipped+<reason>`.
- [x] Every refreshed consumer has a passing expected-platform install audit
  and local validation before PR creation. HOA Manager's Docker/Postgres-backed
  E2E lane was unavailable locally and passed in GitHub CI before merge.
- [x] Every merged consumer is green and comment-clean, and post-merge
  provenance reports `0.15.5` with a passing 134-target install audit.
- [x] Every touched consumer checkout ends clean on its default branch matching
  the remote, with the refresh branch removed locally and remotely.
- [x] A final fleet preflight and status table identify any remaining stale
  consumer and the exact follow-up required; otherwise all six are at target.

## Rollout Results

| Consumer | Before | Result | Evidence | Final |
| --- | --- | --- | --- | --- |
| `platypeeps/anomaly-metric-creator` | `0.15.2` | `refreshed+merged` | [PR #244](https://github.com/platypeeps/anomaly-metric-creator/pull/244), merged 2026-07-16T23:56:27Z | `0.15.5` |
| `platypeeps/hoa-manager` | `0.15.3` | `refreshed+merged` | [PR #107](https://github.com/platypeeps/hoa-manager/pull/107), merged 2026-07-17T00:09:21Z | `0.15.5` |
| `platypeeps/loadsmith` | `0.15.4` | `refreshed+merged` | [PR #74](https://github.com/platypeeps/loadsmith/pull/74), merged 2026-07-17T00:36:40Z | `0.15.5` |
| `answerbook/mezmo_benchmark` | `0.8.6` | `refreshed+merged` | [PR #345](https://github.com/answerbook/mezmo_benchmark/pull/345), merged 2026-07-16T23:09:36Z | `0.15.5` |
| `platypeeps/rwbp-coordinator` | `0.8.6` | `refreshed+merged` | [PR #111](https://github.com/platypeeps/rwbp-coordinator/pull/111), merged 2026-07-16T23:32:29Z | `0.15.5` |
| `platypeeps/rwbp-website` | `0.8.6` | `skipped+dirty-worktree` | Untracked `.trellis/tasks/07-15-rwbpr-024-gdpr-compliance-readiness/` | `0.8.6` |

## Remaining Follow-Up

The website checkout must be made clean by the owner of the untracked GDPR
planning task. Then rerun `sd-fleet-refresh consumer=rwbp-website` from this
checkout. Do not stash, delete, or absorb that task as part of the rollout.

## Notes

- This is operational rollout work. Consumer product changes and upstream
  Trellis changes are out of scope.
- The Answerbook consumer remains in scope because it is explicitly present in
  the checked-in fleet manifest.
- The task id retains its original `0.15.0` suffix. Five child releases landed
  before consumer rollout completed, so the final fleet target advanced to the
  tagged `0.15.5` release.
- Loadsmith CI exposed a timing-sensitive MQTT debounce test and an opaque DMG
  packaging failure. PR #74 added deterministic task-backed test synchronization
  and package-log diagnostics; all 456 Swift tests and the package gate passed.
