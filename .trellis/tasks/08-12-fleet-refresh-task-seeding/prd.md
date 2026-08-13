# Seed fleet-refresh consumer tasks with real PRD and context entries

## Goal

Every fleet-refresh lane creates a dedicated Trellis task in the consumer, by
hand, following prose in `.agents/skills/sd-fleet-refresh/SKILL.md`. Four
defects recur across lanes, each surfacing at `focused-candidate` or later --
or, for the fourth, only after the task is archived -- rather than at
`checkout-validation` where the task is created. Each costs a
diagnose-and-repair round inside an otherwise green lane.

Defects 1-3 were observed on `platypeeps/rwbp-coordinator` PR 222 (campaign
`refresh-0.71.2-20260813T002259Z`) and again on `platypeeps/loadsmith` and
`platypeeps/anomaly-metric-creator` (campaign
`refresh-0.71.2-20260813T014138Z-c3`). Defect 4 is not part of that set: it was
first observed on `platypeeps/hoa-manager` PR 247, later the same day, and only
after that PR's completion bundle had already been published — which is the
point of the entry below.

## The four defects

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

   Confirmed live on mezmo_benchmark, 2026-08-13: `task.py create` run on the
   refresh branch stamped `base_branch: chore/sd-ai-command-pack-0.71.2`, and
   that same checkout rejected `--base-branch` with `unrecognized arguments`.
2. **Empty `task.json` description.** `SKILL.md` already requires asserting a
   non-empty description before advancing the stage, and calls it "a
   belt-and-suspenders guard against an upstream `task.py create` that tolerates
   an empty description". The guard is prose with no mechanical enforcement, so
   it can be and was skipped; anomaly-metric-creator reached `focused-candidate`
   with `field description must be a non-empty string`.
3. **Placeholder planning artifacts.** `task.py create` seeds `prd.md` with
   `- TBD` requirements and empty acceptance criteria, and seeds
   `implement.jsonl` / `check.jsonl` with a single `_example` scaffold row.

   The two halves are not equally covered, and an earlier draft of this entry
   said they were. The ready gate at `.trellis/workflow.md:424` is scoped to the
   manifests only — "both `implement.jsonl` and `check.jsonl` must contain at
   least one real entry before `task.py start`" — and it is prose, with nothing
   executing it.

   The review preflight's `_example` rule covers less than it appears to. It
   rejects a scaffold row **mixed with real rows**, but exempts a manifest whose
   *only* row is the untouched scaffold — `isPristineTrellisTaskContextScaffold`
   in `scripts/sd-ai-command-pack-review-preflight.mjs`, consulted by
   `validateBookkeepingTaskContexts` —
   deliberately, because at merge time that shape is indistinguishable from an
   unfilled manifest, and failing it produced a late completion-time failure. A
   freshly seeded consumer task is exactly the exempt shape, so for the case
   this task is about, the rule does not fire.

   Nothing anywhere rejects a `TBD` PRD: `TBD` occurs
   in exactly one file under `scripts/**` and `.trellis/scripts/**`, and that
   occurrence is `task_store.py:199-213` *writing* the placeholder. So the PRD
   half has no owner at all — not a prose gate, not a mechanical one.
4. **Context entries citing the task's own directory.** Filling `implement.jsonl`
   / `check.jsonl` with real entries — defect 3's remedy — invites citing the
   facts the lane just collected, which live under the task being seeded. Those
   paths resolve for the whole life of the task and dangle the instant
   `task.py archive` moves the directory.

   This one does not surface at `focused-candidate` at all. It surfaces after
   the completion bundle is published, which is the worst possible time: the
   bundle's span is fixed, so the pointer cannot be corrected without a commit
   past the journal tail or a rewrite of a pushed branch.

## Requirements

1. `SKILL.md`'s `checkout-validation` stage must make `base_branch` explicit
   rather than inherited, by running `task.py set-base-branch <task-dir>
   <default-branch>` immediately after `create`.

   It must **not** instruct `task.py create --base-branch`. That flag ships with
   the same revision that fixes the defect, so on exactly the consumers that
   need it, `create` fails with `unrecognized arguments: --base-branch`
   (observed on mezmo_benchmark, 2026-08-13). `set-base-branch` is present in
   both revisions and is the only universally available remedy.

   Reordering creation before the branch switch is also insufficient: it
   produces the right answer only by accident of which branch happens to be
   checked out.
2. The seeded-task properties must be checked mechanically at
   `checkout-validation`, not left to prose: non-empty `task.json` description,
   `base_branch` equal to the consumer's default branch, planning artifacts
   free of `TBD` placeholders and `_example` scaffold rows — including the
   lone-scaffold shape the merge-time rule deliberately exempts — and the
   citation rule in requirement 5.

   That list is a floor, not a ceiling. Requirement 4 makes the stage invoke the
   preflight's existing task-record validation rather than a filtered copy of
   it, so a seeded task with a malformed `createdAt` or a mismatched `name` also
   fails here. Filtering the shared result down to the fields named above would
   be restating the rule by omission, and those defects fail at
   `focused-candidate` anyway.
3. A seeded-task defect must fail `checkout-validation` with an actionable
   message naming the offending field and its repair, rather than advancing and
   surfacing later as a review-preflight failure.
4. The check must not duplicate the review preflight's own rules. Where the
   preflight already defines a rule, the stage check should invoke or share it
   so the two cannot drift apart.
5. A seeded task's `implement.jsonl` / `check.jsonl` must not cite a path under
   its **own** task directory. `task.py archive` moves the whole directory, so
   such a citation resolves while the task is active and dangles the moment the
   task completes — in the same bundle that publishes it.

   The review preflight's existing rule does not catch this. It restricts
   context references to `.trellis/spec/**` or `.trellis/tasks/**/research/**`,
   and its allowed-root test — `isTrellisTaskContextReference` in
   `scripts/sd-ai-command-pack-review-preflight.mjs` — is
   `/^\.trellis\/tasks\/(?:archive\/\d{4}-\d{2}\/)?[^/]+\/research(?:\/.+)?$/`,
   a shape test that never compares the cited task against the
   citing one, and that accepts the archive form too. Passing that rule is
   exactly how the defect gets published.

   The remedy is a narrowing, not a new root: reject a citation whose task
   directory is the citing file's own. `.trellis/spec/**` is unaffected,
   because specs do not move on archival.

   This narrowing is not total, and the requirement should not claim it is. A
   *sibling* task's `research/**` can dangle later, when that sibling archives.
   What the narrowing removes is the deterministic case — the one that fails on
   every seeded task, in the same bundle that publishes it — not every archival
   hazard. The residual is a citation that outlives the run that wrote it, which
   is ordinary cross-task reference rot and not this task's to solve.

   Where a seeded task's context genuinely is task-local — the managed-scope
   facts a refresh lane collects — the check must name the alternative rather
   than only refuse, since "cite a spec instead" is not actionable when the
   consumer's specs are all product-domain.

## Constraints

- No change to `task.py`, and no dependence on the skew in defect 1 being closed
  first. The pack does not install vendored Trellis at all: `.trellis/scripts/**`
  appears zero times in a consumer's `.sd-ai-command-pack/installed-targets.txt`.
  No fleet refresh will ever replace the old `task_store.py`, so the stage must
  work with it rather than wait for it.
- The check must not depend on the consumer's *installed* pack revision.
  `checkout-validation` is the first lane stage and `install-update` is the
  second (`scripts/sd-ai-command-pack-fleet-controller.py:44-56`), so at the
  moment the seeded task is validated the consumer still carries the previous
  release. A gate implemented as a new subcommand and invoked from the
  consumer's own copy would exit `2` with `unknown review-preflight command` on
  exactly the consumers that have not been refreshed yet — the same
  ships-with-the-fix trap as requirement 1's `--base-branch`. The gate is
  therefore run from the pack source checkout against the consumer's task
  directory, the way `sd-ai-command-pack-fleet-review-classify.py` is already
  invoked.
- It must still behave identically on both vendored `task_store.py` revisions,
  since it reads a `task.json` either of them may have written.

## Acceptance Criteria

- [x] Following `SKILL.md`'s `checkout-validation` text literally yields a task
      whose `base_branch` is the consumer's default branch, on a checkout whose
      `task_store.py` lacks `resolve_default_branch` as well as one that has it.
- [x] A task with an empty description fails `checkout-validation` with a
      message naming the field and the repair.
- [x] A `prd.md` retaining `- TBD` requirements, or a `.jsonl` retaining an
      `_example` row, fails `checkout-validation`.
- [x] A correctly seeded task advances without new friction.
- [x] The stage check and the review preflight cannot disagree, because the
      stage check invokes or shares the preflight's rule rather than restating
      it.
- [x] A `.jsonl` citing a path under its own task directory fails
      `checkout-validation`, and the message names a citation the seeded task
      can actually use instead.
- [x] A `.jsonl` citing `.trellis/spec/**`, or a *sibling* task's
      `research/**`, still passes — the narrowing rejects self-reference only,
      and deliberately leaves the sibling-archives-later case alone.

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

Defect 4 is not hypothetical; it was observed twice on 2026-08-13, in two
different gates, from the same mechanic.

- On `platypeeps/hoa-manager` PR 247, the seeded task's `implement.jsonl` and
  `check.jsonl` each cited that same task's own `research/refresh-scope.md`
  (task directory `08-13-sd-ai-command-pack-0-71-2`, under that consumer's
  Trellis task root).
  The review preflight passed on the pre-archive head; GitHub Copilot flagged
  both pointers as dangling in the merged tree, where the file is under
  `.trellis/tasks/archive/2026-08/`. It could not be repaired on that branch:
  the completion bundle was already published, so the fix would have needed a
  commit past the journal tail or a rewrite of a pushed bundle.
- In this repository, `.trellis/spec/tooling/fleet-publish-generated-content.md`
  cited the active path of the task that established it, and the finalization
  that published the spec archived that task in the same push. That one was a
  hard CI failure, in a file the archive commit never touched — the preflight's
  `references missing path` check, naming the spec's own line and the
  now-moved task directory — fixed by `67ae00c4`, which repointed the citation
  at `.trellis/tasks/archive/2026-08/08-12-fleet-publish-ignore-block-ordering`.

A third instance surfaced while this very requirement was being written: the
bullet above originally quoted the hoa-manager pointer as a literal
repo-rooted path, and the pack's own documentation path-reference gate failed
on it — `prd.md:169 references missing path`, because that path belongs to
another repository. Rewritten to name the task directory without a repo-rooted
literal.

Three instances in one day, in three different files, caught by three different
gates and only one of them before publication. That is the argument for checking
this at `checkout-validation` rather than trusting authors to remember it.

The second and third instances are a different gate and outside this task's
scope — the pack's documentation path-reference check already enforces those.
They are recorded because they establish that the failure is the archive move
and cross-context path assumption itself, rather than anything specific to
`.jsonl`.

## Notes

Sibling task `08-12-fleet-publish-ignore-block-ordering` covers a different
fleet defect in the same lane: `sd-ai-command-pack-fleet-publish.py` builds the
work commit before the managed `.obsidian-kb` ignore block is regenerated. The
two are independent and separately verifiable.
