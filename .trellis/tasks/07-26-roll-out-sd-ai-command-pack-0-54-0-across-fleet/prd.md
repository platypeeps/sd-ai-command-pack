# Roll out sd-ai-command-pack 0.54.0 across the fleet

## Goal

Deliver the immutable `v0.54.0` sd-ai-command-pack release to every configured
consumer through the deterministic fleet controller, preserving consumer
ownership while using bounded rollout waves, exact-head review and CI gates,
serialized merges, and post-merge audit evidence.

## Background

- `manifest.json` and `.sd-ai-command-pack/manifest.json` declare version
  `0.54.0`.
- `origin` advertises `refs/tags/v0.54.0` at merged source commit
  `163c104b95871dc315a8e643ffa664b00a723bf5`; the local tag cache has not yet
  fetched that tag.
- `docs/FLEET_ROLLOUT.md` is the delivery authority and
  `docs/fleet/consumers.json` is the schema-version-4 fleet authority.
- The selected scope is the complete eight-consumer manifest. Merge mode is
  enabled, release authority is `origin`, and review uses the classifier's
  integration-only profile when proven, with normal remote review as the
  fail-closed fallback.
- The controller, not conversation state, owns campaign identity, action
  ordering, attempts, receipts, exact heads, concurrency, and merge order.

## Requirements

- R1: Fetch the immutable release tag from `origin`, then require controller
  planning and source preflight to validate tag identity, ancestry, payload,
  candidate ledger, fleet manifest, consumer identities, and checkout paths
  before any consumer mutation.
- R2: Create one safe campaign and timing run ID derived from release `0.54.0`
  and the UTC start time. Record and reuse them for the life of this task.
- R3: Execute only current actions issued by the controller and record exactly
  one normalized receipt before requesting additional work. Never edit private
  controller or timing state manually.
- R4: Preserve manifest scheduling: run `rwbp-coordinator`, `loadsmith`, and
  `hoa-manager` as sequential canaries; run `rwbp-website`, `mezmo_benchmark`,
  `se-ai-command-pack`, and `sd-github-review` with maximum concurrency two;
  run `anomaly-metric-creator` alone last. Keep merges serialized in manifest
  order.
- R5: Treat missing, dirty, divergent, or externally owned consumer checkouts
  as bounded ownership outcomes. Never stash, reset, clean, clone, force-push,
  or overwrite unrelated work.
- R6: For each refresh-needed consumer, run only preflight-issued installer and
  audit commands, manifest preparation/check commands, and the consumer's
  documented full local gate. Commit only installer-managed output and
  deterministic repo-owned preparation artifacts; never edit product code.
- R7: Publish or reuse one exact-head refresh PR per eligible consumer. Run the
  source review classifier; use integration-only review only when proven and
  otherwise use normal remote review. Existing feedback and unresolved threads
  remain blocking under either profile.
- R8: Classify every verified finding through the source severity gate. Pause
  new starts and merges for a pack-owned correctness, security, install/audit,
  or compatibility blocker; capture deferred consumer/local work as explicit
  follow-up before continuing.
- R9: Allow only controller-issued housekeeping to merge. Require green
  exact-head checks, zero unresolved review threads, mergeability, finish-work
  evidence where applicable, and post-merge provenance/audit/branch cleanup.
- R10: Maintain timing evidence across preflight and every consumer stage,
  including overlapping reviewer and CI waits. Timing failures pause new
  mutation but never override delivery gates.
- R11: End with controller `validate`, controller `status`, and a complete
  timing report. Report each consumer, scheduling behavior, findings, timing,
  retries, skips, open PRs, blockers, and remaining action explicitly.

## Acceptance Criteria

- [ ] AC1: The controller campaign is bound to immutable release `0.54.0`, all
      eight configured consumers, merge-enabled mode, `origin`, and a valid
      full-fleet preflight receipt.
- [ ] AC2: Every consumer reaches one controller-terminal result such as
      `at-target`, `refreshed-merged`, `ownership-skip`, `pr-open`, `blocked`,
      or `failed`, with exact reason and head/PR evidence when applicable.
- [ ] AC3: Every mutated consumer passed install audit, declared preparation
      and checks, its full local gate, review/thread disposition, and exact-head
      CI before merge or an explicitly recorded non-merge terminal outcome.
- [ ] AC4: Canary, bounded-wave, and serialized-merge policy is preserved; no
      checkout exceeds its single-lane ownership boundary.
- [ ] AC5: No dirty, missing, externally owned, or unrelated consumer work is
      modified, and no consumer product code or upstream Trellis repository is
      changed by this campaign.
- [ ] AC6: Every merged consumer ends clean on its default branch at
      `0.54.0`, passes post-merge install audit, and has its proven refresh
      branch removed and refs pruned.
- [ ] AC7: Controller validation and status succeed, timing is complete for all
      selected consumers, and the final report states every empty category as
      `none`.

## Out of Scope

- Consumer product features, dependency upgrades, or unrelated maintenance.
- Creating missing consumer clones or repairing operator-owned dirty state.
- Rewriting or retagging `v0.54.0`.
- Bypassing controller state, finding classification, review, CI, eligibility,
  or housekeeping gates.
- Creating a pull request in the upstream Trellis repository.
