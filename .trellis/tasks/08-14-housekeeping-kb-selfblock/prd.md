# Housekeeping KB refresh must not block its own merge

Upstream record: issue #432. Observed on pack 0.71.1 in
`platypeeps/se-ai-command-pack` PR #214 during `sd-ship` Stage 4.

## Goal

Stop `sd-housekeeping` from writing to a tracked file before its own
clean-tree merge gate reads tree cleanliness. Today the pre-merge Obsidian KB
refresh can rewrite the managed block in `.gitignore`; the tree goes dirty,
the dependency-PR merge path bails with `working_tree_dirty`, and housekeeping
exits 1 having blocked the merge it was invoked to perform.

## Why now

The trigger is any change to the managed `.gitignore` block content, which
then reproduces on **every consumer at once** on the first housekeeping run
after the change ships. The thin-mode conversion rewrites exactly that
managed block on every converted consumer, so this defect fires fleet-wide
during the thin rollout unless fixed first.

## Requirements

- The KB refresh must not leave a tracked-file delta in place when a merge is
  pending: either run it after the merge, skip the write when the only delta
  is its own managed block and a merge is in flight, or reconcile the write
  before the gate reads cleanliness.
- If a dirty tree still blocks, the anomaly must name the writer that dirtied
  it, not present an unexplained diff.
- Decide and document the single owner of the managed `.gitignore` block:
  issue #432 shows the KB writer and `trellis-provenance` whole-file hashing
  fighting over the same bytes (write -> drift -> revert -> write loop).

## Non-goals

- Changing the clean-tree gate's failure-closed posture for deltas the run
  did not itself write.
- Any change to KB content generation.

## Acceptance Criteria

- [ ] A housekeeping run whose KB refresh changes only the managed
      `.gitignore` block still performs an otherwise-eligible merge.
- [ ] A dirty tree from any other writer still blocks, and the anomaly names
      the dirty paths and (when housekeeping wrote them) the writing step.
- [ ] The managed-block ownership rule is written down where both the KB
      writer and the provenance guidance point at it.
- [ ] A regression test reproduces the issue #432 sequence (refresh rewrites
      banner -> merge still proceeds).
- [ ] Issue #432 is closed by the shipping PR.
