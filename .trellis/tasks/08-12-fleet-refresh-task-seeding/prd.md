# Seed fleet-refresh consumer tasks with real PRD and context entries

## Goal

Every fleet-refresh lane creates a dedicated Trellis task in the consumer, by
hand, following prose in `.agents/skills/sd-fleet-refresh/SKILL.md`. Three
defects recur across lanes, each surfacing at `focused-candidate` or later
rather than at `checkout-validation` where the task is created. Each costs a
diagnose-and-repair round inside an otherwise green lane.

Observed on `platypeeps/rwbp-coordinator` PR 222 (campaign
`refresh-0.71.2-20260813T002259Z`) and again on `platypeeps/loadsmith` and
`platypeeps/anomaly-metric-creator` (campaign
`refresh-0.71.2-20260813T014138Z-c3`).

## The three defects

1. **`base_branch` records the refresh branch**, because of vendored-Trellis
   version skew. Every consumer checked carries a `task_store.py` whose
   `create` writes `"base_branch": current_branch` unconditionally
   (`.trellis/scripts/common/task_store.py:325` in rwbp-coordinator,
   hoa-manager, and loadsmith; `resolve_default_branch` appears zero times in
   any of them). This pack's own checkout carries the later revision, which
   resolves `origin/HEAD` first and only falls back to the checked-out branch
   with a warning (`task_store.py:333-346`, issue #399 item 1). So the defect is
   invisible when reasoning from the source tree and reproducible in the fleet.

   `SKILL.md` compounds it by ordering the stage as "create one isolated refresh
   branch" and then "create and activate one dedicated lightweight Trellis
   task": on a skewed consumer, following it literally stamps the refresh branch
   as the PR target. The pack's review preflight rejects that at
   `focused-candidate` under its root-task rule, `root task base_branch must
   equal the repository default branch`. Repaired by hand on rwbp-coordinator;
   avoided on the two later lanes only because the operator already knew.
2. **Empty `task.json` description.** `SKILL.md` already requires asserting a
   non-empty description before advancing the stage, and calls it "a
   belt-and-suspenders guard against an upstream `task.py create` that tolerates
   an empty description". The guard is prose with no mechanical enforcement, so
   it can be and was skipped; anomaly-metric-creator reached `focused-candidate`
   with `field description must be a non-empty string`.
3. **Placeholder planning artifacts.** `task.py create` seeds `prd.md` with
   `- TBD` requirements and empty acceptance criteria, and seeds
   `implement.jsonl` / `check.jsonl` with a single `_example` scaffold row. The
   ready gate in `.trellis/workflow.md` rejects both; the review preflight
   independently rejects a changed context file that "still contains a generated
   `_example` scaffold row", but says nothing about a `TBD` PRD.

## Requirements

1. `SKILL.md`'s `checkout-validation` stage must make `base_branch` explicit
   rather than inherited, by passing the consumer's resolved default branch to
   `task.py create --base-branch` (or setting it immediately after). Reordering
   creation before the branch switch is not sufficient: it produces the right
   answer only by accident of which branch happens to be checked out, and the
   stage must be correct on both vendored `task_store.py` revisions without
   knowing which one the consumer carries.
2. The three seeded-task properties must be checked mechanically at
   `checkout-validation`, not left to prose: non-empty `task.json` description,
   `base_branch` equal to the consumer's default branch, and planning artifacts
   free of `TBD` placeholders and `_example` scaffold rows.
3. A seeded-task defect must fail `checkout-validation` with an actionable
   message naming the offending field and its repair, rather than advancing and
   surfacing later as a review-preflight failure.
4. The check must not duplicate the review preflight's own rules. Where the
   preflight already defines a rule, the stage check should invoke or share it
   so the two cannot drift apart.

## Constraints

- No change to `task.py`, and no dependence on the skew in defect 1 being closed
  first. The pack does not install vendored Trellis at all: `.trellis/scripts/**`
  appears zero times in a consumer's `.sd-ai-command-pack/installed-targets.txt`.
  No fleet refresh will ever replace the old `task_store.py`, so the stage must
  work with it rather than wait for it.
- The check runs inside the consumer, so it may only rely on what an installed
  consumer has, and must behave identically on both vendored `task_store.py`
  revisions.

## Acceptance Criteria

- [ ] Following `SKILL.md`'s `checkout-validation` text literally yields a task
      whose `base_branch` is the consumer's default branch, on a checkout whose
      `task_store.py` lacks `resolve_default_branch` as well as one that has it.
- [ ] A task with an empty description fails `checkout-validation` with a
      message naming the field and the repair.
- [ ] A `prd.md` retaining `- TBD` requirements, or a `.jsonl` retaining an
      `_example` row, fails `checkout-validation`.
- [ ] A correctly seeded task advances without new friction.
- [ ] The stage check and the review preflight cannot disagree, because the
      stage check invokes or shares the preflight's rule rather than restating
      it.

## Verification

Each criterion is checkable against a scratch consumer checkout by seeding the
defect deliberately and running the stage check; none requires a live campaign.
The first criterion needs both vendored revisions, and both are available today:
any consumer checkout supplies the old one, and this pack's own
`.trellis/scripts/common/task_store.py` supplies the new one. The old revision is
not a symptom of a stale pack — loadsmith is at pack `0.71.2` and still carries
it — so pick the fixture by grepping `task_store.py` for
`resolve_default_branch`, never by pack version.

The last criterion is verified by reading both call sites and confirming a
single rule source, not by observing that two independent implementations happen
to agree on one sample.

## Notes

Sibling task `08-12-fleet-publish-ignore-block-ordering` covers a different
fleet defect in the same lane: `sd-ai-command-pack-fleet-publish.py` builds the
work commit before the managed `.obsidian-kb` ignore block is regenerated. The
two are independent and separately verifiable.
