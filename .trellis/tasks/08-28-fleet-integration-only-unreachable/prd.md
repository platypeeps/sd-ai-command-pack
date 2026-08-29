# Integration-only fleet review is unreachable by construction

## Goal

`sd-ai-command-pack-fleet-review-classify.py` exists to prove that a consumer
refresh branch is a pure installer-managed change and therefore eligible for
`integration-only` review instead of `remote-review-required`. It has never
returned `integration-only` for a lane this workflow produced, and it cannot,
because the publisher that builds the reviewed head always writes paths the
classifier counts as consumer-owned. Either the classifier should exclude the
publisher's own bookkeeping, or the eligibility contract should be retired as
unreachable.

## Evidence

Observed 2026-08-29 on the parked `mezmo_benchmark` lane of campaign
`fleet-0.71.63-20260829T025500Z` (base `a7bc846c`, head `0e392b0a`, PR #550),
which is a plain thin-pin refresh carrying no product-code change:

```
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  sd-ai-command-pack-fleet-review-classify.py \
  --consumer mezmo_benchmark --repo <checkout> \
  --base-commit a7bc846cc76e5759d14d5eea873ceecd284e03b1 --json
```

```json
"eligible": false,
"disallowedPaths": [
  ".trellis/tasks/archive/2026-08/08-28-refresh-sd-ai-command-pack-to-0-71-63/check.jsonl",
  ".trellis/tasks/archive/2026-08/08-28-refresh-sd-ai-command-pack-to-0-71-63/implement.jsonl",
  ".trellis/tasks/archive/2026-08/08-28-refresh-sd-ai-command-pack-to-0-71-63/prd.md",
  ".trellis/tasks/archive/2026-08/08-28-refresh-sd-ai-command-pack-to-0-71-63/task.json",
  ".trellis/workspace/sdelmas/index.md",
  ".trellis/workspace/sdelmas/journal-3.md"
],
"reasons": ["consumer-owned or unclassified paths changed: ..."]
```

Established facts:

- The six disallowed paths are the *only* reason for ineligibility. The
  installer-managed receipts are accepted, and `docs/repomix-map.md` is
  accepted as deterministic preparation output — it is not in the list.
- Every one of those six paths is written by
  `sd-ai-command-pack-fleet-publish.py` itself, as the task archive and
  journal that its own `--work-message-file` / record-session step produces.
  No human and no product change contributed them.
- Because publication folds that bookkeeping into the reviewed head before the
  classifier ever runs, the disallowed set is non-empty on every lane by
  construction. All seven publishing lanes of this campaign, and every lane of
  the preceding campaigns, classified `remote-review-required`.

## Relationship to the head-advance task

This is a *content* defect and is distinct from
`08-28-fleet-lane-head-advance-by-construction`, which is a *sequencing*
defect about the head moving after the review record. They share the
observation that finalization output lands in the reviewed head, but they have
different symptoms, different guards, and different fixes; neither fix implies
the other. Cross-reference them rather than merging them.

## Requirements

- Decide the intended contract. Either:
  (a) the classifier's allowlist should recognize the publisher's own
      finalization output — the active task's archive directory and the
      journal/index paths for the invoking developer — as installer-managed
      rather than consumer-owned; or
  (b) `integration-only` is genuinely unreachable for this publication shape
      and the eligibility path should be removed rather than left as dead
      contract that every lane silently fails.
- If (a), the allowlist must stay narrow. It must admit only the archive
  directory of the lane's own task slug and the journal/index of the invoking
  developer, so an unrelated Trellis edit smuggled into the same branch still
  forces `remote-review-required`.
- Do not weaken the classifier by allowing `.trellis/**` wholesale.

## Acceptance Criteria

- [ ] The intended contract is decided and recorded, with the reasoning stated.
- [ ] If (a): a lane carrying only installer receipts, deterministic preparation
      output, and its own task archive plus journal classifies `integration-only`.
- [ ] If (a): a lane that additionally edits an unrelated `.trellis/` task still
      classifies `remote-review-required`, covered by a regression test.
- [ ] If (b): the eligibility path and its callers are removed, and no caller is
      left asking a question that cannot be answered affirmatively.
- [ ] The decision is cross-referenced from
      `08-28-fleet-lane-head-advance-by-construction`.
