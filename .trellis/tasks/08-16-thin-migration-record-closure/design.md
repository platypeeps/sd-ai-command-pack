# Design: closing the thin-migration records

Implements `prd.md` in this directory. Every change is to a planning artifact;
no code, no generated payload, no fleet mutation.

## The only real design question

`prd.md` names one risk: this task's deliverable is edits to *other* active
tasks' `prd.md` files — its parent's and its grandparent's — and the
finalization validator applies per-path lifecycle rules to active-task
directories. The requirement was to settle the finalization mode before
implementation rather than discover it at the merge gate. This is that
settlement, read out of
`scripts/sd-ai-command-pack-review-preflight.mjs` rather than assumed.

**Decision: `--mode planning`.** The bundle is a planning finalization over
task artifacts plus a journal session. It is not `completion` — nothing is
archived, no task reaches `completed`.

## Why planning mode accepts a cross-task batch

Four rules govern what a planning bundle may touch. Each is satisfiable here,
and the one that looked most likely to block does not apply.

1. **`planning_task_layout_invalid` (`:2504`)** — "planning task change must
   remain in an active supported task directory". Both `08-09-thin-migration`
   and `08-09-deployment-thin-consumers` are active (`planning`) task
   directories, not archive paths, so edits to their `prd.md` are in-bounds.
   The rule constrains *where* a changed task lives, not *whose* task it is;
   there is no same-directory restriction to violate.

2. **`planning_archive_mutation` (`:2500`)** — no archived task is touched.
   The seven archived children of `08-09-thin-migration` are cited as evidence
   and never modified.

3. **`planning_lifecycle_mutation` (`:2533`)** — "planning task must keep
   status planning, completedAt null, and branch null". This is the rule that
   answers `prd.md` requirement 5: **the parent stays `planning`**, not as a
   preference but because moving it inside this bundle would trip this check.
   Ticking acceptance criteria is a `prd.md` edit and never writes `task.json`,
   so the criteria can all be settled without touching lifecycle state.

4. **`planning_active_task_outside_closure` (`:2556`–`:2584`)** — the rule this
   task was filed nervous about. A changed planning task that links to a task
   outside the changed set blocks **only when that neighbour is `in_progress`
   or `review`** (`:2580`); a `planning` neighbour is explicitly not a
   violation. Measured: zero tasks in this repository are `in_progress` or
   `review`. The grandparent's other children —
   `08-09-machine-status-copy-unavailable` and `08-09-plugin-closure-size` —
   are both `planning`, so pulling the grandparent into the changed set does
   not drag them in.

Rule 4 is the one to re-measure at implementation time. It depends on live task
status across the whole repository, which any other session can change; the
other three depend only on this batch's own contents.

## Changed closure

| path | change |
| --- | --- |
| `.trellis/tasks/08-09-deployment-thin-consumers/prd.md` | replace the stale blocker header (lines 3–10) |
| `.trellis/tasks/08-09-thin-migration/prd.md` | tick criteria 1, 3, 5 with evidence; resolve 2 either way per D2; annotate 4 |
| `.trellis/tasks/08-16-thin-migration-record-closure/**` | this task's own artifacts |
| `.trellis/workspace/sdelmas/journal-8.md` + sibling index | the finalization journal |

No `task.json` in that set changes status, `completedAt`, or `branch`.

## D1 — what replaces the blocker header

Not deletion. The header records a real constraint that really governed the
rollout order — it is why AMC was sequenced into the final cohort — and the
count it carries is corroborated: the archived `08-11-pack-layout-aware-guard`
independently measured 175 blockers for `anomaly-metric-creator` on 2026-08-14
and records the correction from an earlier figure of 207. Deleting the header
would erase the sequencing rationale from the program's top-level task while
that measurement survives in an archive nobody reads first.

(An earlier draft of this paragraph claimed
`08-10-thin-final-conversion-gate-retirement` cites the same count. It does not;
that task carries no 175. The corroborating record is the archived guard task.)

It becomes a resolution note in the past tense: what was blocked, what
dispositioned it, and the ledger state that supersedes it — all eight consumers
`passed` in `docs/fleet/candidate-validation.json`. The distinction the
validator and the reader both care about is present-tense blocker versus
recorded history, and the requirement-4 sweep in
`08-10-thin-final-conversion-gate-retirement` establishes the same rule for doc
surfaces: historical text may stay and must read as history.

## D2 — evidence standard for ticking

`prd.md` requirement 4 forbids copying its own assessment table. The table was
built from archived children and a script reading; three of its five rows were
never re-measured in the session that wrote them. Concretely, at implementation
time:

- **criterion 1** — resolve the canary consumer's converted state and its CI
  outcome from the archived child's own recorded evidence, not from the parent's
  summary of it.
- **criterion 2** — the revert rehearsal is asserted from session memory in this
  task's `prd.md` and has no citation in this checkout. Treat it as *unproven*
  until located. If no durable record exists, say so and leave the criterion
  unticked rather than ticking it on recollection.
- **criterion 3** — verifiable at AMC's post-merge HEAD by grepping its
  `.github/workflows/`; the deletions are merged.
- **criterion 5** — read `.github/scripts/prepare-release.py` for the candidate
  check invocation and the raise that blocks on failure.

Criterion 2 is the one likely to fail this standard. That is the intended
outcome of the requirement, not a problem with it: a criterion that cannot be
evidenced should stay open.

## D3 — criterion 4 stays unticked, and says why

It gets an annotation naming `08-10-thin-final-conversion-gate-retirement`
requirement 2 as the outstanding half, and the unresolved premise recorded
there: retiring `validate_consumer` removes the only consumer validator while
`--revert-thin` remains live and documented as the prescribed recovery route,
so a consumer following the documented path would land in a state nothing
validates. Three options are already written up in that task; this task selects
none of them. Deciding here would move an engineering judgment into a
bookkeeping change.

## Citations

Every `path:line` this task adds must resolve in this checkout — the CI scope
preflight resolves citations against the local tree, so a cross-repo path fails.
AMC's workflow state is evidence for criterion 3 but lives in another
repository. Record it as a repository plus PR or commit reference — the form
cross-repo evidence takes — rather than as a `path:line` that cannot resolve
here. This is not a weaker standard for that criterion: a repo-qualified PR
reference is checkable, a dangling local path is not.

## Rollback

`git revert`. No state outside the task records changes, so a revert restores
the prior records exactly and costs nothing beyond the re-measurement effort.

## Verification

- The three edited `prd.md` files re-read after editing, confirming no
  present-tense blocker survives and that criterion 4 is still unticked.
- `git diff` over the batch confirming no `task.json` status, `completedAt`, or
  `branch` field moved.
- A repository-wide re-measure of task statuses immediately before finalization,
  confirming rule 4's precondition still holds.
- `final-bundle --mode planning` returning `planning_bundle_valid`.
- `make check`.
