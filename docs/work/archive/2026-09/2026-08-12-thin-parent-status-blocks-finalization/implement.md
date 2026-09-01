# Implement: unblock finalization for the thin-consumers tree

One branch, `fix/thin-parent-status-finalization`, three commits in the
order D3 fixes. No code, no generated artifacts, no consumer contact.

## Recovery source

The corrected parent text already exists, verified, in two commits that
are reachable from closed PR #434 and confirmed present in this checkout
2026-08-12:

- `d386f250` — `08-09-deployment-thin-consumers/prd.md` (+41/-), plus
  the two child files already merged by #436.
- `d3b34c8b` — `08-09-deployment-thin-consumers/design.md` (+23/-) and a
  one-line `prd.md` citation fix.

Recover with `git show <sha>:<path>` per file rather than cherry-picking:
both commits also touch the child files that #436 already landed in
different final form, so a cherry-pick would conflict or regress them.

## Steps

### 1. Branch and flip the parent to `planning`

```bash
git checkout main && git pull --ff-only
git checkout -b fix/thin-parent-status-finalization
```

Edit `.trellis/tasks/08-09-deployment-thin-consumers/task.json`:
`status` `in_progress` → `planning`. Assert `completedAt` and `branch`
are already `null` rather than writing them.

```bash
python3 ./.trellis/scripts/task.py validate \
  .trellis/tasks/08-09-deployment-thin-consumers
python3 -c "import json;d=json.load(open('.trellis/tasks/08-09-deployment-thin-consumers/task.json'));assert (d['status'],d['completedAt'],d['branch'])==('planning',None,None),d"
git commit -- .trellis/tasks/08-09-deployment-thin-consumers/task.json
```

Commit message records D1 and the enumeration behind it.

### 2. Land the parent's doc corrections

Take **both files from `d3b34c8b`**, the later of the two commits. It is
a descendant of `d386f250`, so its `prd.md` already carries that
commit's rewrite plus the archived-path citation fix — verified
2026-08-12, one match each for `Pi retention holds` and for
`archive/2026-08/08-09-thin-machine-installer`. `d386f250` is named in
this plan as where the rewrite was authored, not as something to apply;
restoring from it would regress the citation.

```bash
for f in prd.md design.md; do
  git show "d3b34c8b:.trellis/tasks/08-09-deployment-thin-consumers/$f" \
    > ".trellis/tasks/08-09-deployment-thin-consumers/$f"
done
```

Then add, in `prd.md`, the D5 recurrence note beside the existing
sentence "this task is not the implementation target": that the task
stays `planning` for the program's duration and is started only if it
acquires direct work of its own.

Verify the four PRD-named correction sites are present, by grep and not
by reading:

```bash
grep -n 'Pi retention holds' .trellis/tasks/08-09-deployment-thin-consumers/prd.md
grep -c '08-09-plugin-closure-size\|08-09-machine-status-copy-unavailable\|08-09-codex-home-skills-family' \
  .trellis/tasks/08-09-deployment-thin-consumers/prd.md   # expect 3
grep -rn '"codex", "pi"' .trellis/tasks/08-09-deployment-thin-consumers/   # expect no output
grep -rn '08-09-thin-machine-installer/research' .trellis/tasks/08-09-deployment-thin-consumers/   # expect no output
ls .trellis/tasks/08-09-thin-machine-installer 2>&1   # expect: No such file or directory
ls .trellis/tasks/archive/2026-08/08-09-thin-machine-installer/research/platform-verification.md
```

```bash
make full-check          # expect 0 failure(s)
git add .trellis/tasks/08-09-deployment-thin-consumers && git diff --cached --check
git commit
git push -u origin fix/thin-parent-status-finalization
```

The push is required before step 3: `journal-only-recovery` proves only
already-published work commits.

### 3. Finalization

Capture the base **before** recording anything:

```bash
BASE=$(git rev-parse HEAD)
```

Record the session with the pack wrapper, citing steps 1 and 2's commits.
The summary states plainly that #436's merged work carries no journal
session, that finalization could not run for it, and that this session
does not retroactively cover it — PRD requirement 4 is discharged by
recording the gap, not by citing another branch's commits, which would
fail the per-path rules.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-record-session.py --title ... --summary ... \
  --commit "<step1>,<step2>" --change ... --test ... --no-commit
git add -- .trellis/workspace/sdelmas/journal-8.md .trellis/workspace/sdelmas/index.md
git diff --cached --check
git commit -m "chore: record journal" -- \
  .trellis/workspace/sdelmas/journal-8.md .trellis/workspace/sdelmas/index.md
```

```bash
FINISH_WORK_RECEIPT="$(mktemp)"
node scripts/sd-ai-command-pack-review-preflight.mjs \
  final-bundle --mode planning --base "$BASE" --head "$(git rev-parse HEAD)" \
  --json >"$FINISH_WORK_RECEIPT"
```

**This is the gate the whole task exists to pass.** Require
`schemaVersion: 1`, `status: valid`, `reasonCodes == ["planning_bundle_valid"]`,
`evidence.headOid == $(git rev-parse HEAD)`. Any other result stops here
with its reason codes; do not widen the base, do not switch modes, and
do not delete the archive/journal commits.

### 4. Prove both directions

PRD acceptance requires a parent-only branch **and** a child-only branch
each to validate — #435 proved that fixing one does not fix the other.
Step 3 covers the parent-only direction.

**Replaying #435's range does not work, and the reason matters.** The
plan originally called for re-running the recorded failure directly:

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs \
  final-bundle --mode planning --base 8d67ff71 --head 3de90a2b --json
```

Executed 2026-08-12 against the pre-fix tree, that returns
`indeterminate` / `bundle_head_not_checked_out`. The validator requires
the bundle head to be the checked-out commit, and it reads the changed
task record and closure neighbours from the **working tree** rather than
from the head ref. So satisfying it means checking out `3de90a2b` —
which restores the pre-fix `task.json` along with everything else, and
the check would fail for the original reason no matter how thoroughly
the fix works. A replay cannot observe this fix. Do not spend time
pinning `3de90a2b` for it.

The pre-fix evidence therefore stays historical, and it is already
recorded rather than needing reproduction: #435's own run produced
`planning_active_task_outside_closure` naming
`.trellis/tasks/08-09-deployment-thin-consumers/task.json`, and CI's
`CI scope` job failed on the same validator, which is what left that PR
`BLOCKED`. Both are cited in `prd.md`.

The child direction is therefore **constructed** on top of the fix, on a
throwaway branch off this one, and the report says so plainly rather
than claiming a replay:

```bash
git checkout -b tmp/child-direction-proof
# touch exactly one child of the parent, e.g. append a line to
# .trellis/tasks/08-09-thin-migration/design.md
git commit -- .trellis/tasks/08-09-thin-migration/design.md
CHILD_BASE=$(git rev-parse HEAD)
# record a journal session citing it, commit journal + index
node scripts/sd-ai-command-pack-review-preflight.mjs \
  final-bundle --mode planning \
  --base "$CHILD_BASE" --head "$(git rev-parse HEAD)" --json
```

Require `status: valid` and `reasonCodes == ["planning_bundle_valid"]`.
This is weaker than a replay — it is a fixture built after the fix — so
its value comes entirely from being the same *shape* as #435: a bundle
whose changed task is a child of the parent, with the parent outside the
changed closure. That is the exact condition the closure rule rejected.

Then delete the branch and its journal entry; it is a probe, not work to
ship. Confirm `main`'s journal file is untouched afterwards.

### 5. Roll out

```bash
gh pr create --body-file <written file>   # never --body
```

Request Copilot, converge its findings, wait for green, then merge
**through `sd-housekeeping`** with the retained receipt:

```bash
bash scripts/sd-ai-command-pack-housekeeping.sh \
  --finish-work-receipt "$FINISH_WORK_RECEIPT" --json
```

That path was unavailable for #434/#435/#436 and its availability here
is the task's real deliverable. If housekeeping still refuses, the fix
is incomplete — report its typed verdict rather than merging by hand.

One known hazard on that path: issue **#432**, "sd-housekeeping blocks
its own merge: pre-merge KB refresh dirties `.gitignore`, tripping the
clean-tree gate". Running the KB refresh before invoking housekeeping,
and committing any resulting `.gitignore` change with the step-2 commit,
avoids meeting it mid-merge. That is a workaround for a filed defect,
not a fix for it.

Delete the receipt file after housekeeping consumes it.

## What this does not do

- The canary conversion. It needs its own per-cohort user authorization
  and mutates three consumer repositories.
- The `completion_successor_history_non_linear` half of the wall, owned
  by `08-09-update-branch-linearity-conflict`.
- Any change to `validatePlanningClosureActiveTasks`. D2 rejects it.

## Rollback

Revert the branch. The status flip is one field and the corrections are
prose; nothing generated, no installer surface, no consumer contact.
