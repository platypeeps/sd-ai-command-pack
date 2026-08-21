# Fleet refresh archives tasks with unchecked acceptance criteria

## Goal

Stop the fleet refresh flow from publishing archived Trellis tasks whose
acceptance criteria are all still unticked, so a merged archive stops
reporting verified work as unverified.

## Context

`scripts/sd-ai-command-pack-fleet-publish.py` folds the work commit, the task
archive, and the journal into one pushed head. Nothing in that path ever
ticks the PRD's acceptance criteria, and nothing in the fleet-refresh skill
asks the operator to. The generated refresh PRD carries five, so every
consumer's archive lands with five empty boxes beside a task marked
`completed`.

Copilot caught this independently on the 0.71.38 rollout, reviewing
se-ai-command-pack PR 257: "This archived task is marked completed, and the
journal/test plan record the audit, self-test, executable-bit check, and
zero-blocker gate disposition, but every acceptance criterion remains
unchecked. That makes the archive report completed work as unverified."

It was ticked by hand on se-ai-command-pack PR 257 and sd-github-review
PR 109. It was **not** on anomaly-metric-creator PR 395 or hoa-manager
PR 279, which merged with the boxes empty — so the defect is already in two
consumers' history, and hand-ticking is demonstrably not a reliable control.

## Requirements

- Decide where the tick belongs. Two candidates, and they are not equivalent:
  the publish helper could tick criteria it can itself prove (it already knows
  the head, the mode, the audit result, and the receipt), or the skill could
  require the operator to reconcile them before publish. The first is
  automatic and cannot lie about what it checked; the second covers criteria
  no helper can evaluate. A refresh PRD's five criteria are not all of one
  kind, so the answer may be both.
- Never tick a box the run did not actually verify. An archive that reports
  unverified work is the defect being fixed; an archive that reports *falsely*
  verified work is strictly worse, and would be introduced by a blanket
  tick-everything pass.
- Whatever the mechanism, it must fail closed: a criterion that cannot be
  evaluated stays unticked and is visible, rather than being silently dropped.

## Acceptance Criteria

- [ ] A fleet refresh published through the helper lands an archive whose acceptance criteria reflect what the run actually verified.
- [ ] A criterion the run could not verify is still visibly unticked, and the publish path says so rather than failing silently.
- [ ] Regression coverage proves both halves: a verified criterion is ticked, an unverifiable one is not.
- [ ] The two consumers already carrying empty boxes in merged history are either corrected or consciously left, with the choice recorded here.
