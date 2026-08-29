# Design: backlog consolidation

## Approach

Pure `.trellis/**` bookkeeping change executed as one branch + PR. No code,
docs, or template edits (delegated to 08-08-phase0-dead-surface-cleanup).

## Disposition mechanics

- **Drop**: `git rm -r` the task directory. Git history preserves content; the
  PR description carries the per-task rationale (copied from prd.md tables).
  `task.py archive` is NOT used for drops because `cmd_archive`
  (`.trellis/scripts/common/task_store.py:481`) force-sets
  `status=completed` — a false record for rejected work.
- **Absorb**: before deleting the source dir, append an `## Absorbed:
  <source-slug>` section to the survivor's prd.md carrying only the unique
  evidence and acceptance criteria named in the PRD table. Do not merge full
  PRDs — survivors stay readable. Where source and survivor contracts
  conflict, the PRD table records the resolution explicitly (recompute-wins
  for the review-check pair; open-question and phase-2 carries for the two
  preflight pairs) — never copy a superseded AC as if it still binds.
- **Archive**: `task.py archive <dir> --no-commit` for the two genuinely
  shipped tasks only (their status=completed is truthful). `--no-commit`
  because the branch commit is authored once at the end.
- **Park**: prefix title with `PARKED:` in task.json and prd.md H1. No other
  edits.
- **Priority edit**: task.json `priority` field only; title edits also update
  prd.md H1 to keep the title-consistency check green.

## Topology safety

The live link field in task.json is `children` (plus `parent` on the child
side); `subtasks` is legacy and empty across the active set. Deleting a child
whose parent survives leaves a dangling `children` entry; deleting a parent
whose child survives leaves a dangling `parent`.

The complete surviving-parent → dropped-child edge set (host-verified scan,
2026-08-08) is exactly four:

1. 07-22-integrate-routed-review-backends → 07-25-add-routed-review-operator-ux
2. 07-22-integrate-routed-review-backends → 07-25-publish-local-review-attestations
3. 07-22-streamline-sd-skill-workflows → 07-22-validate-sd-workflow-program-integration
4. 07-22-streamline-sd-skill-workflows → 07-25-add-multi-reviewer-learning-and-effectiveness-analysis

Order of operations: unlink those four via `task.py remove-subtask`; delete
dropped subtrees leaf-first (dropped→dropped edges vanish with their dirs);
scripted post-check that every remaining task.json's `parent` and `children`
(and legacy `subtasks`) values resolve to an existing active or archived dir.

Archive side effects, per `cmd_archive` (`task_store.py:485-491`): an archived
task STAYS in its parent's `children` list by design (children missing from the
active set are treated as completed), and only its own active children get
their `parent` field cleared. Concretely: archiving
07-22-evaluate-sd-github-review-consolidation clears `parent` on its surviving
child 07-22-integrate-routed-review-backends; archiving
07-24-correct-sd-skill-contract-drift leaves it listed in
07-22-streamline-sd-skill-workflows' `children`, which is expected — the
topology post-check accepts references that resolve to archived dirs. The
parent-clearing mutation is captured by the step-1 snapshot diff.

## New-task seeding

`task.py create "<title>" --slug <slug>` for the ten new tasks, then fill
task.json description (non-empty — the create-time empty-description defect is
itself in the backlog) and replace the template prd.md with a problem statement
citing this review's evidence plus initial requirements. New tasks stay
`planning`; no design/implement docs yet (they get their own planning cycles).

08-08-parallel-work-backlog and 08-08-fleet-one-path carry the owner's stated
requirements verbatim (worker count user-specified; one path for
Trellis/pack/GitHub/workflow across fleet).

## CI / merge path

Branch from main, single commit, PR. First push classifies full-mode CI
(action != synchronize forces it) — accepted; the diff is .trellis-only so the
suite is unaffected. Preflight lanes that fire on Trellis changes (topology,
metadata, manifests) are the real gate and are run locally first.

## Rollback

Single revert of the one commit restores all 79 tasks. No generated artifacts,
no manifest or payload digest involvement (no template/script changes).

## Risks

- A dropped task later turns out to be wanted: recover via
  `git log --diff-filter=D` + checkout of the deleted path; PR description
  indexes every deletion.
- Absorb sections drift from source intent: mitigated by copying the source's
  own AC text, not paraphrasing.
- Title/priority edits may trip the preflight task-metadata integrity lane:
  run preflight locally before push (AC 1).
