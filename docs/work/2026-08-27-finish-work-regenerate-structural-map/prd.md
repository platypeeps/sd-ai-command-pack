---
title: Regenerate the consumer structural map in sd-finish-work
status: planning
created: 2026-08-27
---
# Regenerate the consumer structural map in sd-finish-work

## Goal

Teach `sd-finish-work` to regenerate the consumer's generated structural map as its
final step — after archive and after the journal — and to compute the receipt at
base-equal-to-head whenever it does.

## Background

A consumer that keeps a generated repository map (e.g. `docs/repomix-map.md`, produced
by a `repomix`-style generator and pinned by a drift test) hits a pincer between two
gates that cannot both be satisfied by reordering commits:

1. The drift test requires the map to equal the post-archive file set.
2. `validateBookkeepingFinalBundle` rejects any finalization-range path outside
   `.trellis/tasks/` and `.trellis/workspace/` as `bundle_scope_invalid`
   (`plugins/sd/bin/sd-ai-command-pack-review-preflight.mjs:1453-1455`).

Regenerate before the archive and the map is stale after it. Regenerate after and the
finalization bundle is invalid.

If `sd-finish-work` owned the regeneration as its final step and computed the receipt at
base-equal-to-head, the map update would be inside a range the validator accepts, and the
consumer would not need a local workaround at all.

## Evidence

Three observed instances in `answerbook/mezmo_benchmark`: PR #483, PR #511, PR #544.
Consumer-side mitigation shipped as PR #546, which sidesteps the pincer with a containment
invariant (excluding both bookkeeping prefixes from the inventory) rather than solving the
ordering problem. That mitigation is sound but per-consumer; this task is the general fix.

## Requirements

- `sd-finish-work` regenerates the consumer's structural map as its final step, after
  archive and journal.
- The receipt is computed at base-equal-to-head whenever regeneration runs, so the map
  update does not widen the finalization delta.
- Consumers with no configured structural-map generator are unaffected — the step is a
  no-op, not an error.
- Touches `plugins/sd/skills/sd-finish-work/SKILL.md` and its mirrored copies under
  `plugins/sd/machine-payload/`, `templates/`, `.agents/`, and `.claude/`. All mirrors
  must stay in sync.

## Acceptance Criteria

- [ ] A consumer with a generated structural map can archive a task and finalize in one
      `sd-finish-work` run with neither a stale-map drift failure nor `bundle_scope_invalid`.
- [ ] A consumer with no structural-map generator finalizes unchanged, with no new step
      reported and no new failure mode.
- [ ] Every mirrored copy of the skill carries the same content; the mirror-sync check passes.

## Related

- Pack follow-up B: `.trellis/tasks/08-27-structural-map-check-final-bundle`
- Pack follow-up C: `.trellis/tasks/08-27-export-bookkeeping-prefixes`
- Consumer task, in the answerbook/mezmo_benchmark repository and not a path here: task 08-06-finalization-repomix-ordering
